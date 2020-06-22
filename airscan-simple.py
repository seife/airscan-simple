#!/usr/bin/python3
#
# This is a simple tool to scan pages from an AirScan compatible scanner.
# I mostly wrote it to debug issues of my Brother MFC-L2710DW device.
# You probably want the excellent sane backend from
# https://github.com/alexpevzner/sane-airscan.git instead.
# All the knowledge about the AirScan protocol has been learned from
# looking at sane-airscan, so I'll license this also as GPL-2.0-or-later
#
# (C) 2020 Stefan Seyfried <seife@tuxbox-git.slipkontur.de>
# see LICENSE file,
# SPDX-License-Identifier: GPL-2.0-or-later
#
import argparse
import json
import sys
import time
import urllib
import xmltodict

URL = 'http://brother/eSCL'

def build_scansettings_xml(source, resolution, docformat, colormode, extformat=True):
    xml = '<?xml version="1.0" encoding="UTF-8"?>' + \
          '<scan:ScanSettings xmlns:pwg="http://www.pwg.org/schemas/2010/12/sm" ' + \
          'xmlns:scan="http://schemas.hp.com/imaging/escl/2011/05/03">' + \
          '<pwg:Version>2.0</pwg:Version>' + \
          '<pwg:InputSource>' + source + '</pwg:InputSource>' +\
          '<pwg:ScanRegions>' + \
          '<pwg:ScanRegion>' + \
          '<pwg:ContentRegionUnits>escl:ThreeHundredthsOfInches</pwg:ContentRegionUnits>' + \
          '<pwg:Height>3507</pwg:Height>' + \
          '<pwg:Width>2550</pwg:Width>' + \
          '<pwg:XOffset>0</pwg:XOffset>' + \
          '<pwg:YOffset>0</pwg:YOffset>' + \
          '</pwg:ScanRegion>' + \
          '</pwg:ScanRegions>' + \
          '<pwg:DocumentFormat>' + docformat + '</pwg:DocumentFormat>' + \
          ( '<pwg:DocumentFormatExt>' + docformat + '</pwg:DocumentFormatExt>' if extformat else '') + \
          '<scan:ColorMode>' + colormode + '</scan:ColorMode>' + \
          '<scan:XResolution>' + resolution + '</scan:XResolution>' + \
          '<scan:YResolution>' + resolution + '</scan:YResolution>' + \
          '</scan:ScanSettings>'
    return xml

# http://brother/eSCL/ScannerCapabilities
def get_scanner_caps(url):
    conn = urllib.request.urlopen(url + '/ScannerCapabilities')
    response = conn.read()
    caps = xmltodict.parse(response)
    return caps['scan:ScannerCapabilities']

def post_scanrequest(url, source, resolution, docformat, colormode):
    post_url = url + '/ScanJobs'
    headers = {}
    headers['Content-Type'] = 'application/x-www-form-urlencoded'
    request = build_scansettings_xml(source, resolution, docformat, colormode)
    #print(request)
    post_data = bytes(request, 'ascii')
    count = 0
    while True:
        try:
            response = urllib.request.urlopen(url = post_url, data = post_data)
            break
        except urllib.error.HTTPError as e:
            if e.code == 503:
                print('Scanner seems busy (HTTP 503), waiting ' + str(count) + ' of 100 seconds', end='\r')
                count += 1
                time.sleep(1)
                if count < 100:
                    continue
                sys.exit(1)
            raise
    if count > 0:
        print()
    headers = response.info()
    return headers['location']

def fetch_result(location, outfile='./out.pdf', multi = False):
    count = 1
    while True:
        if multi:
            # better add a format string...
            name = outfile.split('.')
            ext = name.pop()
            filename = '.'.join(name) + '-' + str(count) + '.' + ext
        else:
            filename = outfile
        try:
            time.sleep(1)
            print("retrieving " + filename)
            urllib.request.urlretrieve(url = location + '/NextDocument', filename = filename)
            count += 1
            if not multi:
                break
        except urllib.error.HTTPError as e:
            if e.code == 404:
                break
            raise

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Scan from an AirScan capable scanner')
    parser.add_argument('-u', '--url', help='URL of the scannner, defaults to http://brother/eSCL', default=URL)
    parser.add_argument('-s', '--source', help='scanner source, can be "Flatbed", "ADF" (default) or "DuplexADF"', default='ADF')
    parser.add_argument('-r', '--resolution', help='scan resolution in dpi (default 300)', default='300')
    parser.add_argument('-f', '--format', help='output format, pdf (default) or jpg', default='pdf')
    args = parser.parse_args()
    scan_caps = get_scanner_caps(args.url)
    have_flatbed = False
    have_adf = False
    have_duplex = False
    flatbed = False
    adf = False
    duplex = False
    multifile = False
    if 'scan:Platen' in scan_caps:
        if 'scan:PlatenInputCaps' in scan_caps['scan:Platen']:
            have_flatbed = True
    if 'scan:Adf' in scan_caps:
        if 'scan:AdfSimplexInputCaps' in scan_caps['scan:Adf']:
            have_adf = True
        if 'scan:AdfDuplexInputCaps' in scan_caps['scan:Adf']:
            have_duplex = True
    if not have_flatbed and not have_adf and not have_duplex:
        print('no scan source (Flatbed, ADF) found, bailing out')
        sys.exit(1)
    if args.source == 'DuplexADF':
        if not have_duplex:
            print('source DuplexADF not available, only have:')
            print('  ' + ('ADF' if adf else '') + ' ' +('Flatbed' if flatbed else ''))
            sys.exit(1)
        adf = True
        duplex = True
        input_caps = scan_caps['scan:Adf']['scan:AdfDuplexInputCaps']
    elif args.source == 'ADF':
        if not have_adf:
            if not have_flatbed:
                print('source ADF is not available')
                sys.exit(1)
            print('source ADF not available, falling back to Flatbed')
            input_caps = scan_caps['scan:Platen']['scan:PlatenInputCaps']
        else:
            adf = True
            input_caps = scan_caps['scan:Adf']['scan:AdfSimplexInputCaps']
    elif args.source == 'Flatbed':
        if not have_flatbed:
            print('source Flatbed is not available')
            sys.exit(1)
        input_caps = scan_caps['scan:Platen']['scan:PlatenInputCaps']
    else:
        print('invalid source argument: ' + args.source)
        sys.exit(1)
    #print(json.dumps(input_caps))
    # sys.exit(0)
    if adf:
        source = 'Feeder'
        if args.format != 'pdf':
            multifile = True
    else:
        source = 'Platen'
    
    # colorformat could be a commandline option...
    result = post_scanrequest(args.url, source, args.resolution, 'application/' + args.format, 'RGB24')
    #print(result)
    # ...as could outfile...
    outfile = './out.' + args.format
    fetch_result(result, outfile, multifile)
    # print(args.url)
    # print(json.dumps(scan_caps))
