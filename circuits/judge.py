#!/usr/bin/env python3

import os
import sys
import logging
import util
import cvutil
import verifier


class Record:
	pass

def judge0 ():
    global inf

    logging.info('Start of judge0()')
    create_directory_structure()

    logging.info('Writing dummy correction.yml with generic internal error')
    util.write_file('correction/correction.yml', 'veredict: IE\ninternal_error: very severe\n')

    logging.info('Preparing data structures')
    inf = Record()
    inf.dir = os.getcwd()
        
    try:
        inf.hdl = util.read_yml(inf.dir+'/problem/handler.yml')
        inf.pbm = util.read_yml(inf.dir+'/problem/problem.yml')
        inf.iface = cvutil.parse_solution_interface_and_synth()
        inf.sub = util.read_yml(inf.dir+'/submission/submission.yml')
        inf.drv = util.read_yml(inf.dir+'/driver/driver.yml')
    except IOError:
        logging.error("Error on data structures.")
        logging.error('Writting problem error on correction/compilation2.txt.')
        util.copy_file('correction/yosys/solution/yosys.stderr', 'correction/compilation2.txt') 
        raise

    inf.env = {
        'hostname': util.hostname(),
        'username': util.username(),
        'time_beg': util.current_time(),
        'uname':    ' '.join(os.uname()),
        'loadavg':  "%.2f %.2f %.2f" % os.getloadavg(),
    }

    inf.cor = {
        'submission':  inf.sub,
        'problem':     inf.pbm,
        'driver':      inf.drv,
        'handler':     inf.hdl,
        'environment': inf.env,
        'veredict':    'IE',
        'interface':   {},
        'statistics':  {},
        'trace_files': [],
    }
    try:
        c = synthesis()
        inf.env['time_end'] = util.current_time()
        util.write_yml(inf.dir+'/correction/correction.yml', inf.cor)

        if c: # Run correction only if synthesis was successful
            logging.info('Start of correction step.')
            c = interface()
            if c: # Run verifier only if interface matched
                c = verification()
                collect_statistcs()
                
                if not c:
                    logging.info('Error on submission verification.')
                    logging.info('Writting traces to correction/.')
                    move_trace_files()
                    
            else:
                logging.info('Error on submission interface.')
                logging.info('Writting interface differences on correction/interface.diff.')
                util.write_file('correction/compilation1.txt', 'Interface mismatch.')
                util.copy_file('correction/interface.txt', 'correction/interface.diff')
                inf.cor['trace_files'].append('correction/interface.diff')
                
            cleanup()
                
            inf.env['time_end'] = util.current_time()
            logging.info('End of correction step.')
        else:
            logging.info('Synthesis was not successfull.')
            logging.info('Writting synthesis error on correction/compilation1.txt.')
            util.copy_file('correction/yosys/submission/synthesis.stderr', 'correction/compilation1.txt') 
            inf.cor['trace_files'].append('correction/compilation1.txt')
            
    except Exception as e:
        logging.error('exception: ' + util.exc_traceback())
        inf.cor['veredict'] = 'IE'
        inf.cor['internal-error'] = 'exception'
        inf.cor['traceback'] = util.exc_traceback()
        raise
    finally:
        logging.info('Veredict: ' + inf.cor['veredict'])
        logging.info('Writing correction')
        util.write_yml(inf.dir+'/correction/correction.yml', inf.cor)
        logging.info('Copying submision to /correction/program.v')
        util.copy_file('submission/program.v', 'correction/program.v') 
        logging.info('End of judge0()')


def synthesis ():
    """Run the synthesizer on the student's file."""
    global inf

    logging.info('Start of synthesis process.')
    try:
        try:    
            cvutil.execute_with_timeout('yosys', 'driver/yosys/yosys_submission_synthesis.ys', 
                                 stdout="correction/yosys/submission/synthesis.stdout", 
                                 stderr="correction/yosys/submission/synthesis.stderr")
        except TimeoutError:
            return False

        ok = util.file_empty('correction/yosys/submission/synthesis.stderr')
        
        if not ok:
            inf.cor['veredict'] = 'CE'
            
        return ok

    finally:
        logging.info('End of synthesis process.')
        
        
def interface():
    """Check wheter the student's module interface matches that of the teacher."""
    global inf

    logging.info('Start of interface verification')
    try:
        cvutil.parse_submission_interface(inf.iface.name)

        # Use diff to stop if any differences are found
        r = os.system('diff correction/yosys/solution/top_module.iface correction/yosys/submission/top_module.iface > correction/interface.txt')
        r = os.WEXITSTATUS(r)
        if r == 0: # No differences were found
            return True
        elif r == 1: # Some differences found
            inf.cor['veredict'] = 'CE'
            return False
        else:
            raise Exception(util.read_file('interface.txt'))
    finally:
        logging.info('End of interface verification')


def verification ():
    """Run the verifier."""
    global inf
    logging.info('Start of verification process.')
    
    try:
        logging.info("Invoking model verifier")
        r = verifier.prepare_verifier(inf.iface.name)
        if not r:
            raise Exception("Error on verifier preparation")
        
        r = verifier.execute_verifier(inf.iface.name)
        logging.info("Creating verdict.")
        
        if r:
            inf.cor['veredict'] = 'AC'
            logging.info("Accepted answer.")
            return True
        else:
            inf.cor['veredict'] = 'WA'    
            logging.info("Wrong answer, parsing verifier results.")
            r = verifier.parse_results()
            logging.info("Results trace generated.")
            return False
        
    except cvutil.TimeoutException:
        logging.info("Verification too long.")
        inf.cor['veredict'] = 'EE'
        return False
    
    finally:
        logging.info('End of verification process')

def collect_statistcs():
    """Collects the statistical values from the solution and submission."""
    global inf
    logging.info('Start of collect_statistics()')

    try:
        inf.cor['statistics'] = cvutil.get_submission_stats()
        
    finally:
        logging.info('End of collect_statistics()')

def get (opt, default=None):
    global inf
    val = None
    if opt in inf.sub: val, whe = inf.sub[opt], 'submission'
    elif opt in inf.pbm: val, whe = inf.pbm[opt], 'problem'
    elif opt in inf.drv: val, whe = inf.drv[opt], 'driver'
    elif opt in inf.hdl: val, whe = inf.hdl[opt], 'handler'
    else: val, whe = default, 'default'
    if val is None:
        raise Exception('missing option (%s)' % opt)
    info = str(val) + ' ('+whe+')'
    logging.info('using value %s for option %s from %s' % (str(val), opt, whe))
    return val

def move_trace_files():
    """Move the generate trace files into correction/ folder."""
    global inf
    logging.info('Start of move_trace_files()')

    try:
        svg_files = [f for f in os.listdir('correction/traces/') if f.endswith('.svg')]
        json_files = [f for f in os.listdir('correction/traces/') if f.endswith('.json')]

        for i, file in enumerate(svg_files, start=1):
            src_path = os.path.join('correction/traces/', file)
            dest_path = os.path.join('correction/', f"trace{i}.svg")
            util.move_file(src_path, dest_path)
            logging.info('Moving ' + src_path + ' to ' + dest_path + '.')
            inf.cor['trace_files'].append(dest_path)

        for i, file in enumerate(json_files, start=1):
            src_path = os.path.join('correction/traces/', file)
            dest_path = os.path.join('correction/', f"trace{i}.json")
            util.move_file(src_path, dest_path)
            logging.info('Moving ' + src_path + ' to ' + dest_path + '.')
            inf.cor['trace_files'].append(dest_path)
        
    finally:
        logging.info('End of move_trace_files()')

def cleanup ():
    """Delete files that are unnecessary if all went well."""
    global inf
    logging.info('Start of cleanup()')
    try:
        # dump_cleanup()
        # util.del_dir('correction/yosys/')
        # util.del_file('correction/interface.txt')
        util.del_file('driver/yosys/' + inf.iface.name + '.eqy')
    finally:
        logging.info('End of cleanup()')

def dump_cleanup():
    """Delete files all the stack trace from yosys."""
    global inf
    logging.info('Start of dump_cleanup()')
    try:
        util.del_dir('correction/' + inf.iface.name + '/')
    finally:
        logging.info('End of dump_cleanup()')


def create_directory_structure():
    util.mkdir("correction/")
    util.mkdir("correction/yosys/")
    util.mkdir("correction/yosys/submission")
    util.mkdir("correction/yosys/solution")

if __name__ == '__main__':
    os.environ["PATH"] += os.pathsep + "/opt/oss-cad-suite/bin"
    try:
        util.init_logging()
        judge0()
    except Exception as e:
        print(e)
        sys.exit(1)
    else:
        sys.exit(0)
