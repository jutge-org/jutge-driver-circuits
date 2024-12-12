#!/usr/bin/env python3

import logging
import os
import re
import operator
import shlex
import subprocess
import time

# Default timeout for an executed command
DEFAULT_TIMEOUT = 20

# Exceptions
class TimeoutException (Exception): pass


CLK_PORT_NAME = 'clk'
RST_PORT_NAME = 'rst'
DONTCARE_PORT_NAME = '_DontCare'
DONTCARE_PREFIX = '_DontCare_'

NUSMV_KEYWORDS = frozenset([
	"MODULE", "DEFINE", "MDEFINE", "CONSTANTS", "VAR", "IVAR", "FROZENVAR",
	"INIT", "TRANS", "INVAR", "SPEC", "CTLSPEC", "LTLSPEC", "PSLSPEC", "COMPUTE",
	"NAME", "INVARSPEC", "FAIRNESS", "JUSTICE", "COMPASSION", "ISA", "ASSIGN",
	"CONSTRAINT", "SIMPWFF", "CTLWFF", "LTLWFF", "PSLWFF", "COMPWFF", "IN", "MIN",
	"MAX", "MIRROR", "PRED", "PREDICATES", "process", "array", "of", "boolean",
	"integer", "real", "word", "word1", "bool", "EX", "AX", "EF", "AF", "EG", "AG", "E", "F", "O", "G",
	"H", "X", "Y", "Z", "A", "U", "S", "V", "T", "BU", "EBF", "ABF", "EBG", "ABG", "case", "esac", "mod", "next",
	"init", "union", "in", "xor", "xnor", "self", "TRUE", "FALSE", "count"])

def mangle_id(name):
    if name in NUSMV_KEYWORDS:
        return name + "#"
    else:
        return name

class Port:
    """A circuit's external port."""
    def __init__(self, name, dir, width):
        self.name = name
        self.id = mangle_id(name)
        self.dir = dir
        self.width = width

    def __repr__(self):
        return "%s.%s('%s','%s',%s)"%(self.__class__.__module__, self.__class__.__name__,
            self.name, self.dir, self.width)

class Interface:
    """Represents a circuit external interface."""
    def __init__(self, name, ports=None):
        self.name = name
        self.ports = {}
        self.inputs = []
        self.outputs = []
        if ports is not None:
            for p in ports.itervalues():
                self.add_port(p.name, p.dir, p.width)

    def __iter__(self):
        return iter(self.ports)

    def __repr__(self):
        return "%s.%s('%s',%s)"%(self.__class__.__module__, self.__class__.__name__,
            self.name, repr(self.ports))

    def add_port(self, name, dir, width):
        p = Port(name, dir, width)
        if dir == 'input':
            self.inputs.append(p)
        elif dir == 'output':
            self.outputs.append(p)
        self.ports[name] = p

    def del_port(self, name):
        p = self.ports[name]
        if p.dir == 'input':
            self.inputs.remove(p)
        elif p.dir == 'output':
            self.outputs.remove(p)
        del self.ports[name]



def parse_top_module(stdout_path, verilog_path):
    '''Parses a top module using the Yosys output if possible, 
       otherwise returns the first module name on the verilog file.'''
    with open(stdout_path, 'r') as file:
        content = file.read()
    
    hierarchy_start = content.find("=== design hierarchy ===")
    if hierarchy_start != -1:
        hierarchy_content = content[hierarchy_start + len("=== design hierarchy ==="):].strip()
        lines = hierarchy_content.splitlines()
        for line in lines:
            if line.strip():
                return re.split(r'\s+', line.strip())[0]

    module_pattern = re.compile(r'module\s+([a-zA-Z_][a-zA-Z_0-9]*)\s*\(')

    with open(verilog_path, "r") as file:
        for line in file:
            m = module_pattern.match(line)
            if m: 
                return m.group(1) # module name
                
    return None

        
def parse_verilog(path):
    '''Parses a verilog file and returns a list of its modules.'''
    module_pattern = re.compile(r'module\s+([a-zA-Z_][a-zA-Z_0-9]*)\s*\(')
    port_pattern = re.compile(r'^\s*(input|output)\s*(\[\s*(\d+)\s*:\s*(\d+)\s*\])?\s*([a-zA-Z_][a-zA-Z_0-9]*)\s*;')
    
    name = None
    ifaces = {}
    with open(path, "r") as file:
        for line in file:
            m = module_pattern.match(line)
            if m: 
                name = m.group(1)
                if not name in ifaces:
                    ifaces[name] = Interface(name)
            
            p = port_pattern.match(line)
            if p:
                size = 1  # default size
                if p.group(2):  
                    msb = int(p.group(3)) #most significant bit
                    lsb = int(p.group(4)) #least significant bit
                    size = msb - lsb + 1
                
                if not '_DontCare' in p.group(5):
                    ifaces[name].add_port(name=p.group(5), dir=p.group(1), width=size)

    return ifaces

def write_interface (iface, path):
    '''Writes a Interface object to a file.'''
    f = open(path, 'w')
    if not f:
        raise Exception("Cannot create prototype file")

    print('module %s;'%iface.name, file=f)

    # Prototype files are to be sorted by 1) inputs first 2) port name
    for port in sorted(iface.inputs, key=operator.attrgetter('name')):
        print('\t%s [%d] %s;'%(port.dir, port.width, port.name), file=f)
    for port in sorted(iface.outputs, key=operator.attrgetter('name')):
        print('\t%s [%d] %s;'%(port.dir, port.width, port.name), file=f)

    f.close()


def parse_solution_interface_and_synth():
    logging.info('Start of solution interface parsing.')
    try:
        execute_with_timeout('yosys', 'driver/yosys/yosys_solution_parser_and_synthesis.ys', 
                             stdout="correction/yosys/solution/yosys.stdout", 
                             stderr="correction/yosys/solution/yosys.stderr")        
        top_module = parse_top_module("correction/yosys/solution/yosys.stdout", "correction/yosys/solution/solution.v")
        ifaces = parse_verilog("correction/yosys/solution/solution.v")
        for i in ifaces:
            write_interface(ifaces[i], "correction/yosys/solution/" + i + ".iface")
        write_interface(ifaces[top_module], "correction/yosys/solution/top_module.iface")

    except TimeoutError:
        logging.error('Yosys took too long to parse the file.')
        return False
    logging.info('End of solution interface parsing.')
    return ifaces[top_module]

def parse_submission_interface(top_module):
    logging.info('Start of submission interface parsing.')
    try:    
        execute_with_timeout('yosys', 'driver/yosys/yosys_submission_parser.ys', stdout="correction/yosys/submission/yosys.stdout")        
        ifaces = parse_verilog("correction/yosys/submission/submission.v")
        for i in ifaces:
            write_interface(ifaces[i], "correction/yosys/submission/" + i + ".iface")
        
        if not top_module in ifaces:
            top_module = parse_top_module("correction/yosys/submission/synthesis.stdout", "correction/yosys/submission/submission.v")
        write_interface(ifaces[top_module], "correction/yosys/submission/top_module.iface")

    except TimeoutError:
        logging.error('Yosys took too long to parse the file.')
        return False
    logging.info('End of submission interface parsing.')
    return True

class Traits:
    """A circuit's traits (properties)."""
    def __init__ (self):
        self.sequential = False
        self.dont_care = False
        self.dont_cares = set()

def detect_circuit_traits(iface):
    """Gathers a number of properties from the interface of a circuit --whether it is sequential, has a dont care signal, etc.-- and returns them as a dictionary."""
    traits = Traits()

    if CLK_PORT_NAME in iface or RST_PORT_NAME in iface:
        if (CLK_PORT_NAME in iface) ^ (RST_PORT_NAME in iface):
            raise Exception("Both clk and rst must appear in sequential circuits")
        clk = iface.ports[CLK_PORT_NAME]
        rst = iface.ports[RST_PORT_NAME]
        if clk.dir != 'input' or rst.dir != 'input':
            raise Exception("Both clk and rst must be input ports")
        if clk.width != 1 or rst.width != 1:
            raise Exception("Neither clk nor rst must be buses")
        traits.sequential = True

    if DONTCARE_PORT_NAME in iface:
        p = iface.ports[DONTCARE_PORT_NAME]
        if p.dir != 'output':
            raise Exception("'%s' must be an output port"%DONTCARE_PORT_NAME)
        if p.width != 1:
            raise Exception("'%s' port must not be a bus"%DONTCARE_PORT_NAME)
        traits.dont_care = True

    for port in iter(iface.ports):
        if not port.startswith(DONTCARE_PREFIX):
            continue
        p = iface.ports[port]
        if p.dir != 'output':
            raise Exception("'%s' must be an output port"%p.name)
        if p.width != 1:
            raise Exception("'%s' port must not be a bus"%p.name)
        name = port[len(DONTCARE_PREFIX):]
        if not name in iface:
            raise Exception("DontCare port '%s' does not exist"%name)
        if iface.ports[name].dir != 'output':
            raise Exception("DontCare port '%s' must be an output port"%name)

        traits.dont_cares.add(name)

    return traits

def get_submission_stats():
    totals = {
        "NANDs": 0,
        "Internal Signals": 0,
        "Number of cells": 0
    }

    patterns = [
        (r"NAND cells:\s+(\d+)", "NANDs"),
        (r"internal signals:\s+(\d+)", "Internal Signals"),
        (r"Number of cells:\s+(\d+)", "Number of cells")
    ]
    
    with open("correction/yosys/submission/synthesis.stdout", "r") as file:
        lines = file.readlines()

    for line in lines:
        for pattern, label in patterns:
            match = re.search(pattern, line)
            if match:
                value = int(match.group(1))
                totals[label] += value

    return totals

def execute_with_timeout (cmd, args, timeout=DEFAULT_TIMEOUT, stdout=None, stderr=None):
    """Executes the command cmd with arguments args, limiting the execution time."""
    logging.info("Executing '" + cmd + " " + args + "'")

    if stdout is not None:
        stdout = open(stdout, 'w')
    if stderr is not None:
        stderr = open(stderr, 'w')
        
    proc = subprocess.Popen([cmd] + shlex.split(args),
        stdout=stdout, stderr=stderr, close_fds=True)
    del stdout
    del stderr

    c = 0
    while c <= timeout:
        if proc.poll() is not None:  # Process has just terminated
            return proc.returncode
        time.sleep(0.2)
        c += 0.2

    proc.kill()
    raise TimeoutException
