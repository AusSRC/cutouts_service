import os
import sys
import logging
import time
import multiprocessing as mp
import threading
import numpy as np

path = os.path.abspath(os.path.dirname(__file__))
if not path in sys.path:
    sys.path.append(path)


import boto3
from boto3.s3.transfer import TransferConfig
import requests
import urllib3

try:
    from ObjStore.ObjStore import *
    from ObjStore.FITSheader import *
    from ObjStore.get_access_keys import *
except ModuleNotFoundError:
    from ObjStore import *
    from FITSheader import *
    from get_access_keys import *

########################################################################################
#
############################### CLASS URLObject ########################################
#
########################################################################################

class UrlObject(FitsObjStore):
    ''' Class to interface with a specific FITS object within a specific bucket in
        an object store using a presigned URL. This is supplied by the bucket owner.
        Inherits from ObjStore.FitsObjStore
    '''
 
    def __init__(self,url=None,readsize = ONE_G_9):
        """ Unless generating a URL with one of the below class 'create_' methods, 
            you would normally pass in a URL that has been given to you. """
        FitsObjStore.__init__(self,mode="url",readsize=readsize)
        self.url = url
        self.http = urllib3.PoolManager()
        self.start_pos = 0
        self.whole_reads = 0
        self.last_read_size = 0
        self.rawdata = b''
        self.upload_dict = None

    def set_read_sizes(self,bytes_to_read):
        self.whole_reads = int(bytes_to_read // self.readsize)
        self.last_read_size = int(bytes_to_read % self.readsize)
        print("%s reads, last = %s bytes" % (self.whole_reads+1, self.last_read_size))

    def set_start_pos(self,start_byte):
        self.start_pos = start_byte


    def create_presigned_url_download(self,certfile, endpoint, project, bucket, key, expiry=8640000):
        """ Create a presigned URL for downloading from objectstore"""

        (access_id,secret_id,quota) = get_access_keys(certfile,endpoint,project)
        client = boto3.client(service_name='s3',aws_access_key_id=ja3_access_id,aws_secret_access_key=ja3_secret_id, endpoint_url=endpoint)
        url = client.generate_presigned_url( ClientMethod='get_object', Params={ 'Bucket': bucket, 'Key': key}, ExpiresIn=expiry)
        self.url = url
        return url

    def create_presigned_url_upload(self,certfile, endpoint, project, bucket, key, expiry=8640000):
        """ Create an upload dict containing a presigned URL for uploading a file to the objectstore"""
        (access_id,secret_id,quota) = get_access_keys(certfile,endpoint,project)
        client = boto3.client(service_name='s3',aws_access_key_id=access_id,aws_secret_access_key=secret_id, endpoint_url=endpoint)
        response = client.generate_presigned_post(bucket,key,ExpiresIn=expiry)
        self.url = response['url']
        self.upload_dict = response
        return response

    def download_via_URL(self,url=None):
        if not url:
            url = self.url
        tobj = requests.get(url)
        return tobj.content

    def upload_via_URL(self,filename, upload_dict=None):
        if not upload_dict:
            upload_dict = self.upload_dict
        if upload_dict:
            with open(filename, 'rb') as f:
                files = {'file': (filename, f)}
                print('Expecting 204 response')
                response = requests.post(upload_dict['url'], data=upload_dict['fields'],files=files)
                print(f'File upload HTTP status code: {response.status_code}')
        


########################################################################################
############################### END CLASS ##############################################
# For local testing ....

NUM_THREADS = 4

if __name__ == "__main__":

    length = ONE_G_9
    start = ONE_G_9 * 2
    import json
    from get_access_keys import *
 
    # This url expires around 18th October 2022:
    endpoint = 'https://projects.pawsey.org.au'      # objectstore address
 
    url = get_download_URL("my_certs.json",endpoint)
    hdr = FITSheaderFromURL(url)
    obj = UrlObject(url)

    # Size of partition in floats:
    xmin = 0
    xmax = 215
    ymin = 0
    ymax = 215
    zmin = 0
    zmax = 18



    start_time = time.time()
    print("Retrieve %s x %s x %s subcube" %(xmax-xmin+1,ymax-ymin+1,zmax-zmin+1))
    fdata = obj.getPartitionData(xmin,xmax,ymin,ymax,zmin,zmax,hdr,NUM_THREADS)
    timeit = time.time()-start_time

    print("Time for %s floats data retrieval= %s sec" % (len(fdata),timeit))
    print(fdata[0],fdata[6668],fdata[13336],fdata[20004])
 
    sys.exit()


 


             

