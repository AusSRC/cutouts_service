import json
import ast
import time

def __checkURLexpiry(url):
    stamp = float(url.split("Expires=")[1])
    now = time.time()
    if now > stamp:
        return False
    return True

def get_access_keys(filename,endpoint,project):
    ''' Given a json file, endpoint url and project name, 
        return the access key, secret key and quota
    '''
    access_id = ""
    secret_id = ""
    quota = ""

    with open(filename,'r') as cert_file:
        cert_data = json.load(cert_file)
        access = cert_data["endpoints"][endpoint]["projects"][project]
        access_id = access["access"]
        secret_id = access["secret"]
        quota = access["quota"]

    return (access_id,secret_id,quota)

def get_download_URL(filename,endpoint,project,bucket,objname):
    ''' Given a json file and endpoint, return the 
        download URL, if defined. '''

    url = ""
    with open(filename,'r') as cert_file:
        cert_data = json.load(cert_file)
        url = cert_data["endpoints"][endpoint]["projects"][project]["bucket"][bucket]["download_urls"][objname]
        if url == "":
            raise ValueError("URL for download not found")
        if not __checkURLexpiry(url):
            raise ValueError("URL has expired")
    return url

def get_upload_URL(filename,endpoint,project,bucket,objname):
    ''' Given a json file and endpoint, return the 
        upload dict containing the URL, if defined. '''

    upload_dict = {}
    upload_str = ""
    with open(filename,'r') as cert_file:
        cert_data = json.load(cert_file)
        upload_str = cert_data["endpoints"][endpoint]["projects"][project]["bucket"][bucket]["upload_urls"][objname]
        if upload_str == "":
            raise ValueError("URL for upload not found")
        upload_dict = ast.literal_eval(upload_str)

    return upload_dict
    

    
