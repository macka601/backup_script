import argparse
import datetime as t
import json
import os
import os.path as p
import textwrap
import time
from subprocess import PIPE, Popen
from timeit import default_timer as timer

# Some file names to get us going
LOCK_FILE_NAME = "backup.lock"
CONFIG_FILE_NAME = "config.json"
# How long to poll the tar processes to see if they are still going
POLL_FREQ = 10

# A list of required keys for the config.json file
REQD_KEYS = [
    "name",
    "src_path",
    "dest_path",
    "enabled",
]

parser = argparse.ArgumentParser(
      prog='backup_script.py',
      formatter_class=argparse.RawDescriptionHelpFormatter,
      description=textwrap.dedent('''\
         Script for backing up a directory
         
         It will take the config.json file, parse, and tar specified files.
         Ensure all keys are specified, or program will exit.
         '''))
parser.add_argument('-f', '--full', action='store_true', help='Does a full backup of the directory (otherwise incremental)')
parser.add_argument('-v', '--verbose', action='store_true', help='Turns on warnings')
args = parser.parse_args()

try:
    with open(CONFIG_FILE_NAME) as f:
        data = json.load(f)
except FileNotFoundError:
    print("Err! could not load the config.json file, does it exist?")
    exit()

date = t.date.today()
running_procs = []

# Write a lock file, incase something is waiting on us to finish
# its more like an indication we're still busy
if p.exists(LOCK_FILE_NAME):
    print("Err! back up is still running (delete {} if this isn't correct)".format(LOCK_FILE_NAME))
    exit()
else:
    open(LOCK_FILE_NAME, 'a').close()

# Start iterating over the list of items to backup, and kick the tar
# threads off. If an item is missing keys or the paths don't exist,
# let the user know, and move onto the next item.
for item in data["backup_list"]:
    # Check we're not missing any keys from the backup item
    missing_key = 0
    for key in REQD_KEYS:
        if key not in item:
            print("Err: Backup item is missing key: " + key)
            missing_key = 1

    if missing_key:
        continue

    # Are we allowed to do this backup?
    if item["enabled"] is False:
        if args.verbose:
            print("Warning: {} is not enabled, skipping ".format(item['name']))
        continue

    full_destination_path = "{}/{}".format(item['dest_path'], item['name'])
    if not p.exists(full_destination_path):
        os.makedirs(full_destination_path)

    if not p.exists(item['src_path']):
        print("Err: Src path does not exist! Skipping")
        continue

    if args.full:
        file_name = "full-{}-{}.tar.gz".format(item["name"], date)
        snar_file = "{}/{}-{}.snar".format(full_destination_path, item['name'], date)
    else:
        file_name = "i.{}-{}.tar.gz".format(item["name"], date)
        cmd = ['find', full_destination_path, '-name', '*snar']
        output = Popen(cmd, stdout=PIPE).communicate()[0]
        output = output.decode()
        snar_file = output.split('\n')[0]

    dest_path_and_file = "{}/{}".format(full_destination_path, file_name)

    if args.full:
        cmd = ['tar', 'zcPf', dest_path_and_file, '--listed-incremental', snar_file, item['src_path']]
        print("Created full backup file {} from {}".format(dest_path_and_file, item['src_path']))
    else:
        cmd = ['tar', 'zcgPf', snar_file, dest_path_and_file, item['src_path']]
        print("Created incremental backup file {} from {}".format(dest_path_and_file, item['src_path']))

    # Start the tar file process going, keep a record in running_procs, so we can check
    # later that it's finished and work out how long it took, then move onto the next.
    process = Popen(cmd, stdout=PIPE, stderr=PIPE)
    running_procs.append((process, timer(), dest_path_and_file))

while running_procs:
    for proc, start, name in running_procs:
        ret = proc.poll()
        if ret is not None:
            running_procs.remove((proc, start, name))
            elapsed_time = time.strftime("%M mins %S seconds", time.gmtime(timer() - start))
            print("Creating {} took {} to complete".format(name, elapsed_time))
            break
        else:
            time.sleep(POLL_FREQ)

# Remove our lock file, we're done.
os.remove(LOCK_FILE_NAME)
