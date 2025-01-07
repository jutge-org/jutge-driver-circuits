#!/usr/bin/env python3

import json
import logging
import os
import re
import time
import subprocess
import cvutil
import util

# Maximum time to wait for the verifier to finish
MAX_VERIFICATION_TIME = 20

# Exceptions:
class VerificationTooLong (Exception): pass

def prepare_verifier (module):
    with open('driver/yosys/top_module.eqy', 'r') as file:
        content = file.read()

    prepared_test_file = content.replace("top_module", module)
    prepared_test_path = 'driver/yosys/' + module + '.eqy'

    with open(prepared_test_path, 'w') as file:
        file.write(prepared_test_file)
        
    return util.file_exists(prepared_test_path)

def execute_verifier (module):
    """Executes Eqy to verify model, redirecting output to stdout and limiting the execution time."""
    logging.info("Start of Yosys-Eqy execution.")
    
    os.chdir('correction')
    test_file_path = '../driver/yosys/' + module + '.eqy'
    
    cvutil.execute_with_timeout('eqy', test_file_path, 
                    timeout=30,
                    stdout="yosys/eqy.stdout", 
                    stderr="yosys/eqy.stderr")
    
    logging.info("End of Yosys-Eqy execution.")
    
    with open('yosys/eqy.stdout', 'r') as file:
        r = None
        for line in file:
            if "Successfully proved designs equivalent" in line:
                r = True
            elif "Failed to prove equivalence" in line:
                r = False
        
    os.chdir('..')
    return r

def parse_results ():
    """Parses Value Change Dump (VCD) files and generates """
    
    util.mkdir('correction/traces')
    path_to_vcd_files = find_vcd_files()
    for file_path in path_to_vcd_files:
        print(file_path)
        
        destination_path, file_name = generate_clean_vcd(file_path)
        
        svg_filename = "correction/traces/" + file_name + ".svg"
        json_filename = "correction/traces/" + file_name + ".json"
        
        try:
            os.system('sootty "' + destination_path + '" -o > ' + svg_filename)
            
        except Exception as e:
            logging.debug("Failed creating " + svg_filename + " file.")
            logging.debug(e)
        
        if (util.file_exists(svg_filename) and not util.file_empty(svg_filename)):
            logging.debug('File generated: ' + svg_filename)
            
        else:
            util.del_file(svg_filename)
            try:
                r = generate_json_from_vcd(file_path)
                if (r): logging.debug('File generated: ' + json_filename)
                
            except Exception as e:
                logging.debug("Failed creating " + json_filename)
                logging.debug(e)
                return False

    return True


def find_vcd_files():
    induct_traces = subprocess.run(["find", "correction/", "-name", "trace_induct.vcd"], capture_output=True, text=True)
    traces = subprocess.run(["find", "correction/", "-name", "trace.vcd"], capture_output=True, text=True)
    result = str.splitlines(induct_traces.stdout.strip()) + str.splitlines(traces.stdout.strip())
    
    if result == "":
        return None
      
    return result

def generate_clean_vcd(file_path):
    with open(file_path, 'r') as file:
        lines = file.readlines()
    
    var_wire_pattern = re.compile(r"\$var wire (\d+) (n\d+) (\S+) \$end")
    scope_pattern = re.compile(r"\$scope module (\w+) \$end")
    upscope_pattern = re.compile(r"\$upscope \$end")
    enddefinitions_pattern = re.compile(r"\$enddefinitions \$end")
    wires_to_remove = ['t']
    filtered_lines = []
    current_module = []
    inside_definitions = True
    
    for line in lines:
        if inside_definitions:
            if "timescale" in line:
                filtered_lines.append(line)
                continue

            var_match = var_wire_pattern.match(line)
            if var_match:
                wire_width = var_match.group(1)
                wire_number = var_match.group(2)
                wire_name = var_match.group(3)

                if (wire_name == 'okay'):
                    filtered_lines.append(line)
                elif ((not current_module) or wire_name.startswith('__') or wire_name.startswith('_DontCare_')
                        or (current_module[-1] != 'gate' and current_module[-1] != 'gold')):
                    wires_to_remove.append(wire_number)
                else:
                    modified_line = "$var wire " + wire_width + " " + wire_number + " " + current_module[-1] + "." + wire_name + " $end\n"
                    filtered_lines.append(modified_line)
                continue
                
            scope_match = scope_pattern.match(line)
            if scope_match:
                current_module.append(scope_match.group(1))
                filtered_lines.append(line)

            elif upscope_pattern.match(line):
                if current_module: current_module.pop()
                filtered_lines.append(line)
                    
            elif enddefinitions_pattern.match(line): 
                inside_definitions = False
                filtered_lines.append(line)

        else:
            split_line = line.split(' ')
            if (len(split_line) == 1):
                if (split_line[0].startswith('#')):
                    filtered_lines.append(line)
            elif (len(split_line) == 2):
                if (not split_line[1].strip() in wires_to_remove):
                    filtered_lines.append(line)
                    

    strategy = file_path.split('strategies/')[1].split('/')[0]
    destination_path = "correction/traces/" + strategy + ".vcd"
    with open(destination_path, 'w') as file:
        file.writelines(filtered_lines)
        
    return destination_path, strategy

def generate_json_from_vcd(file_path):
    strategy = file_path.split('strategies/')[1].split('/')[0]
    destination_path = "correction/traces/" + strategy + ".json"
    
    input_names, output_names = parse_iface('correction/yosys/submission/' + str(strategy).split('.')[0] + '.iface') 
    
    with open(file_path, 'r') as file:
        lines = file.readlines()
    
    var_wire_pattern = re.compile(r"\$var wire (\d+) (n\d+) (\S+) \$end")
    scope_pattern = re.compile(r"\$scope module (\w+) \$end")
    upscope_pattern = re.compile(r"\$upscope \$end")
    enddefinitions_pattern = re.compile(r"\$enddefinitions \$end")

    current_module = []
    inside_definitions = True
    
    input_wires = {}
    output_gold_wires = {}
    output_gate_wires = {}
    input_values = {}
    output_gold_values = {}
    output_gate_values = {}
    
    for line in lines:
        if inside_definitions:
            var_match = var_wire_pattern.match(line)
            if var_match:
                wire_number = var_match.group(2)
                wire_name = var_match.group(3)

                if (current_module[-1] == 'gold'):
                    if (wire_name in input_names):
                        # print("gold in " + str(wire_name) + " is "  + str(wire_number))
                        input_wires[wire_number] = wire_name
                    elif (wire_name in output_names):
                        # print("gold out " + str(wire_name) + " is "  + str(wire_number))
                        output_gold_wires[wire_number] = wire_name
                        
                elif (current_module[-1] == 'gate'):
                    if (wire_name in input_names):
                        # print("gate in " + str(wire_name) + " is "  + str(wire_number))
                        input_wires[wire_number] = wire_name
                    elif (wire_name in output_names):
                        # print("gate out " + str(wire_name) + " is "  + str(wire_number))                    
                        output_gate_wires[wire_number] = wire_name      
                continue
                
            scope_match = scope_pattern.match(line)
            if scope_match:
                current_module.append(scope_match.group(1))

            elif upscope_pattern.match(line):
                if current_module: current_module.pop()
                    
            elif enddefinitions_pattern.match(line): 
                inside_definitions = False

        else:
            split_line = line.split(' ')
            if (len(split_line) == 2):
                wire_value = split_line[0].strip()
                wire_number = split_line[1].strip()
                
                if (wire_number in input_wires):
                    input_values[input_wires[wire_number]] = int(wire_value[1:], 2)
                    
                elif (wire_number in output_gold_wires):
                    output_gold_values[output_gold_wires[wire_number]] = int(wire_value[1:], 2)
                    
                elif (wire_number in output_gate_wires):
                    output_gate_values[output_gate_wires[wire_number]] = int(wire_value[1:], 2)

    # print(input_wires)
    # print(output_gold_wires)
    # print(output_gate_wires)
    
    if (not input_values and not output_gate_values and not output_gold_values):
        return False
    
    data = {
        "input": input_values,
        "output": output_gate_values,
        "expected": output_gold_values,
    }

    with open(destination_path, 'w') as file:
        json.dump(data, file, indent=2)
    
    return True

def parse_iface(file_path):
    input_list = []
    output_list = []

    with open(file_path) as file:
        lines = file.readlines()

    io_pattern = r'\b(input|output)\s+\[\d+\]\s+(\w+);'

    for line in lines:
        match = re.search(io_pattern, line)
        if match:
            io_type, name = match.groups()
            if (io_type == "input"):
                input_list.append(name)
            elif (io_type == "output"):
                output_list.append(name)
    
    return input_list, output_list

# if __name__ == '__main__':
#     parse_results()