#!/usr/bin/env python3

import logging
import os
import time
import subprocess
import shlex
import util

import cvutil

# Maximum time to synthesize
MAX_SYNTHESIS_TIME = 10

# List of available synthesizers (each class will add itself to this list)
synthesizers = []

# Exceptions
class SynthesisTooLong (Exception): pass
class SynthesisError (Exception): pass


class Synthesizer:
    """Synthesizer base class (abstract)."""

    def __init__ (self, handler):
        self.handler = handler

    def name (self):
        '''Returns the compiler name.'''
        raise Exception('Abstract method')

    def language (self):
        '''Returns the language name.'''
        raise Exception('Abstract method')

    def version (self):
        '''Returns the version of this compiler.'''
        raise Exception('Abstract method')

    def flags1 (self):
        '''Returns flags used for synthesis.'''
        raise Exception('Abstract method')

    def flags2 (self):
        '''Returns a second set of flags used for synthesis.'''
        raise Exception('Abstract method')

    def extension (self):
        '''Returns extension of the source files (without dot).'''
        raise Exception('Abstract method')

    def prepare_synthesis (self, ori):
        '''Copies the necessary files from ori to . to prepare synthesis.'''
        util.copy_file(ori+'/program.' + self.extension(), '.')

    def synthesize (self, module):
        '''Do the actual synthesis of the files in .'''
        raise Exception('Abstract method')

    def execute_synthesizer (self, cmd, args, stdout=None, stderr=None):
        """Executes the command cmd with arguments args, limiting the execution time."""
        logging.info("executing '" + cmd + " " + args + "'")

        if stdout is not None:
            stdout = open(stdout, 'w')
        if stderr is not None:
            stderr = open(stderr, 'w')
        proc = subprocess.Popen([cmd] + shlex.split(args),
            stdout=stdout, stderr=stderr, close_fds=True)
        del stdout
        del stderr

        c = 0
        while c <= MAX_SYNTHESIS_TIME:
            if proc.poll() is not None:  # Process has just terminated
                return proc.returncode
            time.sleep(0.2)
            c += 0.2

        # Synthesis is taking way too long, kill the process.
        proc.kill()
        raise SynthesisTooLong

    def get_version (self, cmd, args, lin):
        """Private method to get a particular line from a command output."""
        stdout = subprocess.run(['yosys', '--version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True).stdout
        return stdout.split(' ')[1]

    def info (self):
        return {
            'compiler_id': self.__class__.__name__.replace('Synthesizer_', '').replace('XX', '++'),
            'name'       : self.name(),
            'language'   : self.language(),
            'version'    : self.version(),
            'flags1'     : self.flags1(),
            'flags2'     : self.flags2(),
            'extension'  : self.extension()
        }


class Synthesizer_Yosys (Synthesizer):
    synthesizers.append('Yosys')

    def name (self):
        return 'Yosys'

    def language (self):
        return 'Verilog'

    def version (self):
        return self.get_version('yosys', '--version', 0)

    def flags1 (self):
        return '-penforce-single-clock=1 -pmodule-prefix=s_'

    def flags2 (self):
        return '-penforce-single-clock=0 -pmodule-prefix=s_'

    def extension (self):
       return 'v'

    def prepare_synthesis (self):
        'Does previous synthesis preparation.'
        
    def synthesize (self):
        try:    
            cvutil.execute_with_timeout('yosys', 'driver/yosys/yosys_submission_synthesis.ys', 
                                 stdout="correction/yosys/submission/synthesis.stdout", 
                                 stderr="correction/yosys/submission/synthesis.stderr")
        except TimeoutError:
            return False
        
        return util.file_empty('correction/yosys/submission/synthesis.stderr')
        
    def info (self):
        return {
            'compiler_id': self.__class__.__name__.replace('Synthesizer_', '').replace('XX', '++'),
            'name'       : self.name(),
            'language'   : self.language(),
            'version'    : self.version(),
            'extension'  : self.extension()
        }


def synthesizer (syn, handler=None):
    '''Returns the synthesizer with id = syn.'''

    return eval('Synthesizer_%s(handler)' % syn)



def info ():
    '''Returns the info on all the synthesizers.'''

    r = {}
    for x in synthesizers:
        r[x] = synthesizer(x).info()
    return r


if __name__ == '__main__':
    util.print_yml(info())
