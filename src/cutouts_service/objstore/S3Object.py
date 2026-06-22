import os
import sys
import time

import boto3
from boto3.s3.transfer import TransferConfig

path = os.path.abspath(os.path.dirname(__file__))
if not path in sys.path:
    sys.path.append(path)

try:
    from ObjStore.ObjStore import *
    from ObjStore.FITSheader import *
except ModuleNotFoundError:
    from ObjStore import *
    from FITSheader import *

PID = os.getpid()


# Openstack authorisation version:
OS_AUTH_VER = '3'

CHUNK16 = ONE_M * 16 # 16Mb
CHUNK128 = ONE_M * 128 # 128Mb
MAX_MEM = ONE_G * 4 # 4Gb for downloading file to memory


##############################################################################################
##############################################################################################
class S3Object(FitsObjStore):
    ''' Class to interface with a specific FITS object within a specific bucket in
        an object store with an S3 interface. Uses the Boto3 library.
        This class uses the Openstack credentials - access_id and secret-key.
        Inherits from ObjStore.FitsObjStore
    '''
    
    def __init__(self,bucket,obj,access_key_id,secret_access,endpoint="https://nimbus.pawsey.org.au:8080"):
        FitsObjStore.__init__(self,mode='s3')
        self.endpoint = endpoint
        self.access =access_key_id # AWS access id number
        self.secret = secret_access # AWS secret key
        self.session = None
        self.client = None
        self.resource = None
        self.session = boto3.session.Session()
        self.client = self.__setClient()
        self.resource = self.__setResource()
        self.threshold = TWO_G
        self.chunksize = TWO_G
        self.threads = 20
        self.bucket = bucket
        self.obj = obj
       
       
########################################################################################################################
## PROTECTED FUNCTIONS #################################################################################################
########################################################################################################################
    def __setClient(self):
        return self.session.client(service_name='s3',aws_access_key_id=self.access, aws_secret_access_key=self.secret, endpoint_url=self.endpoint)
    
    def __setResource(self):
        return self.session.resource(service_name='s3',aws_access_key_id=self.access, aws_secret_access_key=self.secret, endpoint_url=self.endpoint)

    def __setHeaderSize(self,posn=None):
        """ If not posn, assumes  self.__last_byte_pos points to end of header """
        if not posn:
            posn = self.__last_byte_pos
        self.__end_header = posn
        
########################################################################################################################
## PUBLIC FUNCTIONS ####################################################################################################
########################################################################################################################
    
   
    def setConfig(self,threshold=CHUNK16,chunksize=CHUNK16,threads=10):
        ''' Set values for uploading of data to the objectstore.
            These are not used for downloading
        '''
        self.threshold = threshold
        self.chunksize = chunksize
        self.threads = threads

    def setVersioning(self):
        versioning = self.resource.BucketVersioning(self.bucket)
        versioning.enable()

    def suspendVersioning(self):
        versioning = self.resource.BucketVersioning(self.bucket)
        try:
            versioning.suspend()
        except:
            pass 
        
    def uploadFile(self,path,filename,ExtraArgs={"ContentType":"binary/octet-stream"},progress=True):
        ''' Upload file to object store. If larger than 4G, this will 'chunk'
            the file into 'chunksize' bits and upload them in parallel.
            This will overwrite the original object!
        '''
        print(f'path: {path}, filename: {filename}, objname: {self.obj}')
        config = TransferConfig(multipart_threshold=self.threshold, max_concurrency=self.threads, multipart_chunksize=self.chunksize, use_threads=True)
        myfile = path + '/' + filename
        if progress:
            self.client.upload_file(myfile,self.bucket,self.obj,ExtraArgs=ExtraArgs,Config=config,Callback=ProgressPercentage(myfile))
        else:
            self.client.upload_file(myfile,self.bucket,self.obj,ExtraArgs=ExtraArgs,Config=config)

    def getObject(self):
        ''' Return the object (or a part of it in bytes) to caller '''
        tobj = self.readWholeObject()
        return tobj
 
    def rewind(self,indx=-1):
        ''' Set the object position indx. '''
        self.__last_byte_pos = indx
        
    def getReadPosition(self):
        ''' Return the object position indx '''
        return self.__last_byte_pos
        
    def getBytesFromLastPos(self,len):
        """ Similar to a sequential 'read' - get len bytes starting from 
            immediately after the last byte read.
        """
       
        return self.readData(self.__last_byte_pos+1,len) 
       
    def stats(self):
        """ Stats on how much has been read or written to the object. """
        
        print()
        print("************************")
        print("Number of bytes read: ",self.__read_bytes)
        print("Number of bytes written: ",self.__write_bytes)
        print("Last byte pos read/written: ",self.__last_byte_pos)
        print("************************")

   
      
########################################################################################################################
######################### END OsS3Object ###############################################################################
########################################################################################################################
# For local testing ....

NUM_THREADS = 4
LOADFILE = False
 
if __name__ == "__main__":

    import json
    from get_access_keys import *
    obj = None

    endpoint = 'https://projects.pawsey.org.au'      # objectstore address
    project = 'ja3'                                  # objectstore account name
    bucket = "dc2"                            # bucket in the objectstore that holds our object
    key = 'sky_full_v2.fits'                        # object in the object store that we want

    # parse the json file that holds our certs
    (ja3_access_id,ja3_secret_id,quota) = get_access_keys('my_certs.json',endpoint,project)


    # Create a header object from objectstore data
    hdr = FITSheaderFromS3(endpoint,bucket,key,ja3_access_id,ja3_secret_id)

    # Create an S3Object for access to acacia:
    obj = S3Object(bucket,key,ja3_access_id,ja3_secret_id,endpoint)

    if LOADFILE:
        # Upload a test datacube (851Gb) with default chunk size = 2Gb:
        obj.uploadFile('/mnt/shared/scratch','sky_full_v2.fits')
        sys.exit()
    else:
        # 'sky_full_v2.fits' has:
        #    11520 bytes of header
        #    913094611200 bytes of data = 228273652800 floats
        #    for a total of 913094622720 bytes

        # Size of partition to extract from datacube in pixels:
        xmin = 0
        xmax = 215
        ymin = 0
        ymax = 215
        zmin = 0
        zmax = 18

        fdata = None
        start_time = time.time()
        print("Retrieve %s x %s x %s subcube" %(xmax-xmin+1,ymax-ymin+1,zmax-zmin+1))
        fdata = obj.getPartitionData(xmin,xmax,ymin,ymax,zmin,zmax,hdr,NUM_THREADS)
            # for 1170 * 1170 *6668 cube on slurm-node-20:
            #     1 thread = 769.981sec 
            #     2 threads = 375.659sec
            #     5 threads = 170.081sec
            #     8 threads = 109.893sec
            #    10 threads = 94.489sec
            #    15 threads = 87.448sec
            #    20 threads = 86.754sec
            #    22 threads = 86.632sec
            #    25 threads = 88.095sec
            #    30 threads = 87.220sec
            #    32 threads = 87.943sec
            # cf a single instance of SoFiA-2 reading from shared file system = 1871sec
        time_len = time.time() - start_time
        print("Time for %s floats data retrieval= %s sec" % (len(fdata),time_len))
        print(fdata[0],fdata[6668],fdata[13336],fdata[20004])
        # -1.8388047e-05 3.5616416e-05 -2.0865675e-05 3.5012516e-05
        # -1.8388047e-05 -2.8571403e-05 -6.6189073e-06 8.619136e-06
        # 2.1073613e-05 -1.4994539e-05 -4.6664198e-07 -6.248855e-06 
        
        sys.exit()
    
    
    

