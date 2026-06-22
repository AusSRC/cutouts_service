
#   Example of using ObjStore and S3Object.py to get a partition (subcube) from a FITS datacube
#   stored in an objectstore
#
#   - GWHG @ CSIRO, Feb 2023 
#

#!/usr/bin/env python

import os
import sys
import logging
import time
import threading
import re 
import signal
from builtins import TypeError

import numpy as np
import boto3
import json
# import ObjStore
# from ObjStore.get_access_keys import *
# from ObjStore.S3Object import S3Object
# from ObjStore.URLObject import UrlObject
# from ObjStore.FITSheader import FITSheaderFromURL
# from ObjStore.FITSheader import FITSheaderFromS3
# try:

# except ModuleNotFoundError:
from get_access_keys import *
from S3Object import S3Object
from URLObject import UrlObject
from FITSheader import FITSheaderFromURL
from FITSheader import FITSheaderFromS3

# Access codes and object identity
endpoint = 'https://projects.pawsey.org.au'        # objectstore address
project = 'ja3'                                    # objectstore account name
bucket = "dc2"                                     # bucket in the objectstore that holds our object
key = 'sky_full_v2.fits'                           # object in the object store that we want
certfile = "~/my_certs.json"       # File holding access id's for objectstore
NUM_THREADS = 6                                    # Use threading for speedup

hdr = None
Obj = None

# define partition we want - 'sky_full_v2.fits' datacube is 5851 * 5851 * 6668 floats
xmin = 1000
xmax = 1010
ymin = 1000
ymax = 1010
zmin = 51
zmax = 53

# Use a presigned URL or else the account access/secret keys:
USEURL = True

if USEURL: # local(6 threads): 856sec carnaby(24 threads):10sec
    # url = get_download_URL(certfile,endpoint,project,bucket,key)
    url = "https://ingest.pawsey.org.au/cutoutpublic/SB75060.fits"
    hdr = FITSheaderFromURL(url)
    obj = UrlObject(url)
# else: # local(6 threads): 814sec carnaby(24 threads):10sec 
#     (access_id,secret_id,quota) = get_access_keys(certfile,endpoint,project)
#     hdr = FITSheaderFromS3(endpoint,bucket,key,access_id,secret_id)
#     obj = S3Object(bucket,key,access_id,secret_id,endpoint)

start_time = time.time() 

# Get the partition data
obj.setDebugFlag()
fdata = obj.getPartitionData(xmin,xmax,ymin,ymax,zmin,zmax,hdr,NUM_THREADS)

time_len = time.time() - start_time
print("Time for %s floats data retrieval= %s sec" % (len(fdata),time_len))
print(fdata)
# print(fdata[0],fdata[668],fdata[1336],fdata[2004])