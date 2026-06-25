import os
import sys
import multiprocessing as mp
import threading
import numpy as np
try:
    from ObjStore.FITSheader import *
except ModuleNotFoundError:
    from cutouts_service.objstore.FITSheader import *

# Gigabyte definitions:
ONE_M = 1024 **2 # 1 Mb
ONE_G = 1024 ** 3 # 1Gb
ONE_G_9 = int(ONE_G * 1.9) # 1.9 Gb
TWO_G = ONE_G * 2 # 2Gb
FOUR_G = ONE_G * 4 # 4Gb

class ProgressPercentage(object):
    def __init__(self, filename):
        self._filename = filename
        self._size = float(os.path.getsize(filename))
        self._seen_so_far = 0
        self._lock = threading.Lock()

    def __call__(self, bytes_amount):
        # To simplify we'll assume this is hooked up
        # to a single filename.
        with self._lock:
            self._seen_so_far += bytes_amount
            percentage = (self._seen_so_far / self._size) * 100
            sys.stdout.write(
                "\r%s  %s / %s  (%.2f%%)" % (
                    self._filename, self._seen_so_far, self._size,
                    percentage))
            sys.stdout.flush()

########################################################################################
#
############################### CLASS FitsObjStore ########################################
#
########################################################################################

class FitsObjStore:

    ''' Base class for accessing data objects in an object store.  '''

    def __init__(self,mode='s3',readsize = ONE_G_9):
        if readsize > ONE_G_9:
            readsize = ONE_G_9
        self.maxread = readsize
        self.xsize = 0
        self.ysize = 0
        self.zsize = 1
        self.xlen = 0
        self.ylen = 0
        self.zlen = 0
        self.hdrsize = 0
        self.chsize = 0
        self.mode = mode
        self.__read_bytes = 0
        self.__write_bytes = 0
        self.__last_byte_pos = -1 # Position of the last byte that was read (byte numbers start at 0)
        self.__end_header = 0
        self.__stride_len = 0
        self.DEBUG = False
 
    def readData(self,start,length):
        ''' Mode is dependent on child class '''
        data = None
        ranges = None
        obj_content = None
        hdr = {}
        if self.mode == 's3': # Use Boto3 library
            if not start:
                start = self.__last_byte_pos+1
            ranges = "bytes=%s-%s" % (start,start+length-1)
            obj_content = self.client.get_object(Bucket = self.bucket, Key = self.obj,Range=ranges)['Body'].read()
            self.__read_bytes += length
            self.__last_byte_pos = self.__last_byte_pos + length
            return np.frombuffer(obj_content,dtype='>f4',count=-1)
        else: # presigned URL
            if length > ONE_G_9:
                raise ValueError("read request too large!!")
            hdr = {"Range":"bytes=%s-%s" % (start,start+length-1)}
            stream = self.http.request("GET",self.url,headers=hdr)
            return np.frombuffer(stream.data,dtype='>f4',count=-1)

    def setDebugFlag(self):
        self.DEBUG = True

    def unsetDebugFlag(self):
        self.DEBUG = False

    def getObjectHeaders(self,filtered='FITS'):
        response = self.client.head_object(Bucket = self.bucket, Key = self.obj)['ResponseMetadata']['HTTPHeaders']
        flatdict = {}
        if filtered == 'FITS':
            for key in response['ResponseMetadata']['HTTPHeaders']:
                if key.startswith('x-amz-meta-'):
                    newkey = key.split('x-amz-meta-')[1].upper()
                    flatdict[newkey] = response['ResponseMetadata']['HTTPHeaders'][key]
            return flatdict
        else:
            return response
        

    def readWholeObject(self):
        ''' Just return the whole object as stored in the objectstore '''
        obj_content = None
        if self.mode == "s3": # Use Boto3 library
            obj_content = self.client.get_object(Bucket = self.bucket, Key = self.obj)['Body'].read()
        else:
            if length > ONE_G_9:
                raise ValueError("read request too large!!")
            hdr = {}
            obj_content = self.http.request("GET",self.url,headers=hdr)
        
        return obj_content

    def __extractDataFromChannel(self,chdata,xmin,xmax,ymin,ymax):
        ''' Given a channel of pixel data, this extracts the subset of required 
            pixels and returns them.
        '''
        # represent data as a 2D array:
        arr = chdata.reshape(self.ysize,self.xsize)
        # Cut out relevant xy region
        data = np.ravel(arr[ymin:ymax+1,xmin:(xmax+1)])
        return data

    def getWholeChannel(self,xmin,xmax,ymin,ymax,zmin,zmax,ch_number):
        ''' Strategy 1 - see getPartitionData() '''
        # Calc pos of start and size of channel
        readsize = self.chsize*FITS_FLOAT_SIZE
        startpos = self.hdrsize + ((zmin+ch_number)*readsize)
        # Get all the data in the channel
        chdata = self.readData(startpos,readsize)
        # Extract relevant cut-out (xmin,xmax,ymin,ymax)
        data = self.__extractDataFromChannel(chdata,xmin,xmax,ymin,ymax)
        return data

    def getChannelBatches(self,xmin,xmax,ymin,ymax,zmin,zmax,ch_nums,i):
        ''' Strategy 2 - see getPartitionData() '''
        # Calc pos of start and size of channel
        start_ch = zmin + (ch_nums*i)
        readsize = self.chsize*FITS_FLOAT_SIZE*ch_nums
        startpos = self.hdrsize + (start_ch*self.chsize*FITS_FLOAT_SIZE)
        # Get all the data in this set of channels
        # read all the data (ch_nums channels)
        chdata = self.readData(startpos,readsize)
        # now process each channel
        start = 0
        end = start+(self.chsize)
        data = self.__extractDataFromChannel(chdata[start:end],xmin,xmax,ymin,ymax)
        start += (self.chsize)
        end += (self.chsize)

        for j in range(ch_nums-1):
            if self.DEBUG:
                print(i,j,start,end,end-start)
            data = np.concatenate((data,self.__extractDataFromChannel(chdata[start:end],xmin,xmax,ymin,ymax)),axis=0)
            start += (self.chsize)
            end += (self.chsize)
        print(f"Read {i+1}: ch {start_ch} = {self.chsize*FITS_FLOAT_SIZE} bytes per ch, {ch_nums} channels started at byte {startpos}",flush=True)
        return data

    def getChannelByRow(self,xmin,xmax,ymin,ymax,zmin,zmax,ch_num):
        ''' Strategy 3 - see getPartitionData() '''
        data = None
        # Calc pos of start and size of channel
        startpos = self.hdrsize + ((zmin+ch_num)*self.chsize*FITS_FLOAT_SIZE)
        # Calc pos of start of 1st required row in channel
        startpos += FITS_FLOAT_SIZE*(ymin*self.xsize + xmin)
        # Get each row of the channel individually
        readsize = self.xlen*FITS_FLOAT_SIZE
        jumpsize = (self.xsize-self.xlen)*FITS_FLOAT_SIZE
        data = self.readData(startpos,readsize)
        for i in range(self.ylen-1):
            data = np.concatenate((data,self.readData(startpos,readsize)),axis=0)
            startpos += jumpsize
        return data

    def getPartitionDataByStrategy(self,xmin,xmax,ymin,ymax,zmin,zmax,hdr,strategy=2):
        ''' This is NON-THREADED !!

            Get the data representing a subcube from a larger datacube held in objectstore.
            This uses the presigned URL for access to the object. One of 3 read strategies can be 
            employed:
                Strategy 1: getWholeChannel - Read 1 channel at a time and return only the required pixels
                Strategy 2: getChannelBatches - Read multiple channels at a time (limited by RAM size, and return only the required pixels
                Strategy 3: getChannelByRow - Read ONLY the required pixels (requires multiple stream openings).
            Stragegy 2 is recommended.
        '''
       
        data = None
        # Get the header data from the object store:
        header = self.getHeaderDict()
        hdrstr = self.getHeaderBytes().decode() 
        self.hdrsize = self.getHeaderSize()


        self.xsize = int(header["NAXIS1"])
        self.ysize = int(header["NAXIS2"])
        self.zsize = 1
        self.xlen = xmax-xmin+1
        self.ylen = ymax-ymin+1
        self.zlen = zmax-zmin+1

        self.chsize = self.xsize * self.ysize
        gap_to_next_y = (self.xsize-xmax) + xmin

        if int(header["NAXIS"]) == 3:
            self.zsize = int(header["NAXIS3"])
        else:
            self.zsize = int(header["NAXIS4"])

        # Process each required channel in the datacube, depending on selected strategy:
        print("Reading %s channels from datacube" % self.zlen,flush=True)
        if strategy == 1:
            data = self.getWholeChannel(xmin,xmax,ymin,ymax,zmin,zmax,0)
            for i in range(self.zlen-1):
                data = np.concatenate((data,self.getWholeChannel(xmin,xmax,ymin,ymax,zmin,zmax,i)),axis=0)
                if i % 10 == 0:
                    print("Got channel %s data" % (i+zmin+1),flush=True)
        elif strategy == 3:
            data = self.getChannelByRow(xmin,xmax,ymin,ymax,zmin,zmax,0)
            for i in range(self.zlen-1):
                data = np.concatenate((data,self.getChannelByRow(xmin,xmax,ymin,ymax,zmin,zmax,i+1)),axis=0)
                if i % 10 == 0:
                    print("Got channel %s data" % (i+zmin+1),flush=True)
        else:
            # STRATEGY 2
            READ_LIMIT = ONE_G_9
            # Calc number of channels we can read at once (batchsize)
            batch = int(READ_LIMIT // (self.chsize*FITS_FLOAT_SIZE))
            # Calc number of reads
            extra_batch = self.zlen % batch
            num_reads = int(self.zlen // batch)
            print("%s reads of batches of %s channels" % (num_reads,batch))
            if extra_batch > 0:
                print("Plus final read of %s" % extra_batch)
            data = self.getChannelBatches(xmin,xmax,ymin,ymax,zmin,zmax,batch,0)
            for i in range(num_reads-1):
                data = np.concatenate((data,self.getChannelBatches(xmin,xmax,ymin,ymax,zmin,zmax,batch,i+1)),axis=0)
                print("Finished read %s / %s" % (i+1,num_reads))
            if extra_batch > 0:
                data = np.concatenate((data,self.getChannelBatches(xmin,xmax,ymin,ymax,zmin,zmax,extra_batch,i+1)),axis=0)


        return data

    def getPartitionData(self,xmin,xmax,ymin,ymax,zmin,zmax,hdr,num_threads=1):
        ''' Get the data representing a subcube from a larger datacube held in objectstore.
            One of 3 read strategies could be employed:
            Stragegy 2 is used here, as it is the most efficient (see getPartitionDataByStrategy() for details).
        '''
        
        # STRATEGY = 2
        tasks = []
        # Get the header data from the object store:
        header = hdr.getHeaderDict()
        self.hdrsize = hdr.len()
        print(f"header size = {self.hdrsize}",flush=True)

        self.xsize = int(header["NAXIS1"])
        self.ysize = int(header["NAXIS2"])
        self.zsize = 1
        self.xlen = xmax-xmin+1
        self.ylen = ymax-ymin+1
        self.zlen = zmax-zmin+1

        self.chsize = self.xsize * self.ysize

        if int(header["NAXIS"]) == 3:
            self.zsize = int(header["NAXIS3"])
        else:
            self.zsize = int(header["NAXIS4"])

        # Calc number of channels we can read at once (batchsize)
        batch = int(ONE_G_9 // (self.chsize*FITS_FLOAT_SIZE))
        # Calc number of reads
        extra_batch = int(self.zlen % batch)
        num_reads = int(self.zlen // batch)
        print("%s reads of channels in batches of %s" % (num_reads,batch),flush=True)

        # Define tasks
        for i in range(num_reads):
            tasks.append([batch,i])
        if extra_batch > 0:
            print("Plus final read of %s" % extra_batch,flush=True)
            tasks.append([extra_batch,len(tasks)])

        # Sanity check - num_threads should not be greater than the number of tasks, or the number of available threads!
        num_threads = len(tasks) if (num_threads > len(tasks)) else num_threads
        max_threads = os.cpu_count() - 2
        num_threads = max_threads if (num_threads > max_threads) else num_threads

        pool = mp.pool.ThreadPool(processes=num_threads)
        print(f"Thread pool created: {num_threads}",flush=True)
        result_objs = []
        for task in tasks:
            r = pool.apply_async(self.getChannelBatches,(xmin,xmax,ymin,ymax,zmin,zmax,task[0],task[1]))
            result_objs.append(r)
        data = np.concatenate([result.get() for result in result_objs])
        return data

########################################################################################
############################### END CLASS ##############################################




          
