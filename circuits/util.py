#!/usr/bin/env python3

##############################################################################
# Importations
##############################################################################

import os
import time
import shutil
import logging
import traceback
import tempfile
import socket
import yaml
import getpass


##############################################################################
# Init logging
##############################################################################


def init_logging ():
    '''Configures basic logging options.'''

    logging.basicConfig(
        format  = '%s@%s ' % (username(), hostname())
            + '%(asctime)s' + ' [' + '%(levelname)s'+ '] ' +'%(message)s',
        datefmt = '%Y-%m-%d %H:%M:%S',
    )
    logging.getLogger('').setLevel(logging.NOTSET)



##############################################################################
# System utilites
##############################################################################


def username ():
    '''Returns the username of the process owner.'''
    return getpass.getuser()


def hostname ():
    '''Returns the hostname of this computer.'''
    return socket.gethostname()


##############################################################################
# File utilites
##############################################################################


def write_file (name, txt=''):
    '''Writes the file name with contents txt.'''
    f = open(name, 'w')
    f.write(txt)
    f.close()


def read_file (name):
    '''Returns a string with the contents of the file name.'''
    f = open(name)
    r = f.read()
    f.close()
    return r


def del_file (name):
    '''Deletes the file name. Does not complain on error.'''
    try:
        os.remove(name)
    except OSError:
        pass
    
def del_dir (name):
    '''Deletes a directory and its content. Does not complain on error.'''
    try:
        shutil.rmtree(name)
    except OSError:
        pass


def tmp_file ():
    '''Creates a temporal file and returns its name.'''
    return tempfile.mkstemp()[1]


def file_exists (name):
    '''Tells wether file name exists.'''
    return os.path.exists(name)


def file_empty (name):
    '''Tells wether file name exists.'''
    return os.stat(name).st_size == 0

def copy_file (src, dst):
    '''Copies a file from src to dst.'''
    shutil.copy(src, dst)


##############################################################################
# YML utilites
##############################################################################


def print_yml(inf):
    print(yaml.dump(inf, indent=4, width=1000, default_flow_style=False))


def write_yml(path, inf):
    yaml.dump(inf, open(path, "w"), indent=4,
              width=1000, default_flow_style=False)


def read_yml(path):
    return yaml.load(open(path, 'r'), Loader=yaml.FullLoader)


##############################################################################
# Utilies on directories
##############################################################################


def mkdir (name):
    '''Makes the directory name. Does not complain on error.'''
    try:
        os.makedirs(name)
    except OSError:
        pass


##############################################################################
# Utilities on dates and times
##############################################################################


def current_time ():
    '''Returns a string with out format for times.'''
    return time.strftime('%Y-%m-%d %H:%M:%S')


##############################################################################
# Others
##############################################################################


def exc_traceback ():
    '''Similar to traceback.print_exc but return a string rather than printing it.'''

    path = tmp_file()
    f = open(path, 'w')
    traceback.print_exc(file=f)
    f.close()
    r = read_file(path)
    del_file(path)
    return r
