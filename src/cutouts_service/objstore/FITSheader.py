import sys
import requests
import boto3
from astropy.io import fits

ENDHEADER = b'END          '
FITS_HEADER_BLOCK_SIZE = 2880
FITS_HEADER_LINE_SIZE  =   80
FITS_HEADER_LINES      =   36
FITS_HEADER_KEYWORD_SIZE =  8
FITS_HEADER_KEY_SIZE     = 10
FITS_HEADER_VALUE_SIZE   = 70
FITS_HEADER_FIXED_WIDTH  = 20
FITS_FLOAT_SIZE = 4

########################################################################################
############################### CLASS FITSheaderFromFile ###############################
########################################################################################
class FITSheaderFromFile:
    '''Class to get and modify header from a fits file on the local filesystem using astropy '''

    def __init__(self,filepath):
        try:
            self.hdul = fits.open(filepath)
        except OSError:
            self.hdul = None

    def convert2dict(self,hdrpos=0):
        ''' Get the FITS header (by default the primary, hdul=0 one) from the file and 
            convert to a flattened dictionary of strings.
        '''
        if self.hdul:
            flatdict = {"Metadata":{}}
            tmphdr = self.hdul[hdrpos].header
            for key in self.hdul[hdrpos].header:
                strval = str(self.hdul[hdrpos].header[key])
                flatdict["Metadata"][key] = strval
            return flatdict
        return {}

########################################################################################
############################### CLASS FITSheaderFromS3 ################################
########################################################################################
class FITSheaderFromS3:

    '''Class to extract the header from a binary FITS file stored in an object store, using the 
       Boto3 S3 API - data can be represented as a raw string or a <key><value> dictionary.
    '''

    def __init__(self,endpoint,bucket,key,access_key_id,secret_access):
        self.bucket = bucket
        self.key = key
        self.endpoint = endpoint

        self.session = boto3.session.Session()
        self.client = self.session.client(service_name='s3',aws_access_key_id=access_key_id, aws_secret_access_key=secret_access, endpoint_url=self.endpoint)

        in_hdr = True
        begin = 0
        size = FITS_HEADER_BLOCK_SIZE 
        self.hdr_data = b''
        self.length = 0
        self.__last_byte_pos = 0
        self.__read_bytes = 0
        while in_hdr:
            chunk = self.__getData(size,begin)
            self.hdr_data += chunk
            begin += (FITS_HEADER_BLOCK_SIZE)
            if ENDHEADER in chunk:
                in_hdr = False
                self.length = begin
        self.xsize=self.ysize=self.zsize=0
        self.channel_bytes=self.cube_bytes=0
        self.max_byte_no = 0
        return

    def __getData(self,length,start_pos):
        """ Get 'len' bytes of object from 'start_pos'
        """
        ranges = "bytes=%s-%s" % (start_pos,start_pos+length-1)
        obj_content = self.client.get_object(Bucket = self.bucket, Key = self.key,Range=ranges)['Body'].read()
        self.__read_bytes += length
        self.__last_byte_pos = self.__last_byte_pos + length
        return obj_content

    def rawHdrData(self):
        return self.hdr_data
    
    def len(self):
        return self.length
    
    def getHeaderDict(self):
        """ Convert the raw header data to key/value pairs """
        
        header = {}
        header["HISTORY"] = ""
        header["ORIGIN"] = ""
        hdr = self.rawHdrData()
        hdrstr = hdr.decode()
        comment_indx = 0
        
        for i in range(0,len(hdrstr),FITS_HEADER_LINE_SIZE):
            str = hdrstr[i:i+FITS_HEADER_LINE_SIZE]
            # Special cases - 'HISTORY' and 'ORIGIN'
            if str.startswith('HISTORY'):
                str = str[8:]
                header["HISTORY"] += "\n    %s" % str
            elif str.startswith('ORIGIN'):
                str = str.split("=")[1]
                header["ORIGIN"] += str
            elif str.startswith('COMMENT'):
                header["COMMENT_%s" % comment_indx] = str[6:]
                comment_indx += 1
            elif str.startswith('END'):
                break
            else:
                if '=' not in str:
                    continue
                key = str.split("=")[0]
                value = str.split('=')[1]
                # Remove trailing '/' from value
                value = value.replace("\\", "")
                value = value.replace("/", "")
                value = value.strip()
                header[key.strip()] = value
                
        return header


########################################################################################
############################### CLASS FITSheaderFromURL ###############################
########################################################################################

class FITSheaderFromURL:

    ''' Class to extract the header from a binary FITS file stored in an object store, using a 
        presigned URL - data can be represented as a raw string or a <key><value> dictionary.
    '''
    def __init__(self,url):
        self.url = url
        in_hdr = True
        begin = 0
        stop = begin + FITS_HEADER_BLOCK_SIZE - 1
        self.hdr_data = b''
        self.length = 0
        while in_hdr:
            headers={"Range":"bytes=%s-%s" % (begin,stop)}
            r = requests.get(self.url,headers=headers)
            chunk = r.content
            self.hdr_data += chunk
            begin += (FITS_HEADER_BLOCK_SIZE)
            stop += (FITS_HEADER_BLOCK_SIZE)
            if ENDHEADER in chunk:
                in_hdr = False
                self.length = begin

        self.xsize=self.ysize=self.zsize=0
        self.channel_bytes=self.cube_bytes=0
        self.max_byte_no = 0
        return

    def __setCubeData(self,header):
        """ Set some standard stats for the datacube represented by the header. """
        self.xsize = int(header["NAXIS1"])
        self.xsizebytes = self.xsize*FITS_FLOAT_SIZE
        self.ysize = int(header["NAXIS2"])
        self.zsize = 1
        if int(header["NAXIS"]) == 3:
            self.zsize = int(header["NAXIS3"])
        else:
            self.zsize = int(header["NAXIS4"])
  
        self.channel_bytes = self.xsizebytes*self.ysize
        self.cube_bytes = self.channel_bytes*self.zsize
        self.max_byte_no = self.cube_bytes + self.len() - 1


    def rawHdrData(self):
        return self.hdr_data
    
    def len(self):
        return self.length
    
    def getHeaderDict(self):
        """ Convert the raw header data to key/value pairs """
        
        header = {}
        header["HISTORY"] = ""
        header["ORIGIN"] = ""
        hdr = self.rawHdrData()
        hdrstr = hdr.decode()
        comment_indx = 0
        
        for i in range(0,len(hdrstr),FITS_HEADER_LINE_SIZE):
            str = hdrstr[i:i+FITS_HEADER_LINE_SIZE]
            # Special cases - 'HISTORY' and 'ORIGIN'
            if str.startswith('HISTORY'):
                str = str[8:]
                header["HISTORY"] += "\n    %s" % str
            elif str.startswith('ORIGIN'):
                str = str.split("=")[1]
                header["ORIGIN"] += str
            elif str.startswith('COMMENT'):
                header["COMMENT_%s" % comment_indx] = str[6:]
                comment_indx += 1
            elif str.startswith('END'):
                break
            else:
                if '=' not in str:
                    continue
                key = str.split("=")[0]
                value = str.split('=')[1]
                # Remove trailing '/' from value
                value = value.replace("\\", "")
                value = value.replace("/", "")
                value = value.strip()
                header[key.strip()] = value
                
        self.__setCubeData(header)
        return header

########################################################################################
############################### END CLASS ##############################################


       

if __name__ == "__main__":

    hdr_obj = FITSheaderFromURL("https://projects.pawsey.org.au/dc2/sky_full_v2.fits?AWSAccessKeyId=acf82f0144c0414f864550c298d8c4d6&Signature=XW%2B%2FqKpfNzcrjBFjuNfdq2unJpY%3D&Expires=1657502744")
    print(hdr_obj.rawHdrData())
    print(hdr_obj.length)
    hdr = hdr_obj.getHeaderDict()
    for key in hdr:
        print("%s : %s" % (key,hdr[key]))
