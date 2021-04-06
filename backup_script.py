#!/usr/bin/env python3
"""
Name: backup_script.py
Author: Grant McEwan
Description:
    Originally just to first tar up files, and then just commence incremental backups, this
    has grown so that a user only ever really has to specify what directory to backup, and
    if there is any pre/post actions they need doing first/last, eg, dump a database first.

    Each item specified in the config.json file is parsed and is queued to run in its own thread
    in the order pre-action->tar->post-action.
    Ensure all mandatory keys are specified, or program will exit.
    If an item is not enabled, it will be skipped.
"""

import argparse
import collections
import datetime as t
import json
import logging as log
import os
import os.path as p
import subprocess
import sys
import textwrap
import time
from subprocess import PIPE, Popen
import threading
from timeit import default_timer as timer
from typing import NamedTuple

LOCK_FILE_NAME = "backup.lock"
CONFIG_FILE_NAME = "config.json"


class ScriptAction(NamedTuple):
    """
    Named tuple class for storing specific script actions.
    These can then be accessed as eg object_name.preaction
    """
    preaction: str
    postaction: str
    showtime: bool
    log_file: str


def is_valid(_item):
    """ Checks a passed in item has the required fields """
    # A list of required keys for the config.json file
    reqd_keys = [
        "name",
        "enabled",
    ]

    for prop in reqd_keys:
        try:
            getattr(_item, prop)
        except AttributeError:
            log.error("Missing json key: {}".format(prop))
            return False
    return True


class BackupItem:
    """
    Backup item class holds all data about the commands to be run.
    Each command is queued in a thread by calling *.queue_items, then when
    *.start() is called, the job queue is processed.
    """
    def __init__(self, opt):
        self.job_queue = []
        # These are all mandatory parameters and should never be empty at this point
        self.name = opt.name
        self.enabled = opt.enabled
        # optional parameters
        self.src_path = getattr(opt, "src_path", None)
        self.dest_path = getattr(opt, "dest_path", None)
        self.pre_action = getattr(opt, "pre_action", None)
        self.post_action = getattr(opt, "post_action", None)
        self.tar_opts = getattr(opt, "tar_opts", None)
        self.show_time = getattr(opt, "show_time_taken", None)

    def is_enabled(self):
        """ returns enabled state """
        return self.enabled

    def queue_items(self, full_backup=False):
        """ Enqueues items into the job queue to process """
        if self.pre_action:
            self.job_queue.append(self.pre_action)

        if self.src_path and self.dest_path:
            # Now build our tar up to queue
            full_destination_path = "{}/{}".format(self.dest_path, self.name)
            if not p.exists(full_destination_path):
                os.makedirs(full_destination_path)

            if full_backup:
                file_name = "full-{}-{}.tar.gz".format(self.name, date)
                snar_file = "{}/{}-{}.snar".format(full_destination_path, self.name, date)
            else:
                file_name = "i.{}-{}.tar.gz".format(self.name, date)
                cmd = ['find', full_destination_path, '-name', '*snar']
                output = Popen(cmd, stdout=PIPE).communicate()[0]
                output = output.decode()
                snar_file = output.split('\n')[0]

            dest_path_and_file = "{}/{}".format(full_destination_path, file_name)

            tar_opts = 'zcPf'
            if self.tar_opts:
                tar_opts += self.tar_opts

            _built_cmd = ''
            if full_backup:
                _built_cmd = "{0} {1}{2} {3}".format(dest_path_and_file, '--listed-incremental=',
                                                      snar_file, self.src_path)
                log.debug("Creating full backup file {0} from {1}".format(dest_path_and_file,
                                                                        self.src_path))
            else:
                tar_opts += 'g'
                _built_cmd = "{0} {1} {2}".format(snar_file, dest_path_and_file, self.src_path)
                log.debug("Creating incremental backup file {} from {}".format(dest_path_and_file,
                                                                               self.src_path))

            cmd = "tar {0} {1}".format(tar_opts, _built_cmd)
            self.job_queue.append(cmd)
        else:
            log.debug("No src or dest specified, only executing pre and post actions")

        # Check if we have to do something when we're finished
        if self.post_action:
            self.job_queue.append(self.post_action)

    def start(self):
        """ Processes any jobs (sequentially) found in the job queue """
        try:
            for _job in self.job_queue:
                start_time = timer()
                log.debug("Executing cmd:: {0}".format(_job))
                proc = subprocess.Popen(_job, shell=True)
                proc.wait()
                log.debug("job {0} finished".format(_job))
                time_taken = timer() - start_time
                time_format = "%M mins %S seconds"

                # If job too longer than 3599 seconds (1 hr), display hours as well
                if time_taken > 3599:
                    time_format = "%H hrs %M mins %S seconds"
                cmd_time = time.strftime(time_format, time.gmtime(time_taken))
                if self.show_time:
                    log.info("{0} took {1} to complete".format(_job, cmd_time))

        except FileNotFoundError:
            log.error("Could not execute: {0}".format(_job))


def create_backup_items():
    """ Returns a list of items from the config file to be processed """
    item_list = []
    try:
        with open(CONFIG_FILE_NAME) as data:
            j = json.load(data, object_hook=
                          lambda c: collections.namedtuple('Item', c.keys())(*c.values()))

            pre = getattr(j, "pre_script_action", None)
            post = getattr(j, "post_script_action", None)
            showtime = getattr(j, "show_script_time", None)
            new_log = getattr(j, "log_file", "/var/log/backup_script")
            other_actions = ScriptAction(pre, post, showtime, log_file=new_log)
            for bitem in j.backup_list:
                if is_valid(bitem):
                    _item = BackupItem(bitem)
                    item_list.append(_item)

            return item_list, other_actions

    except FileNotFoundError:
        log.error("Err! could not load the config.json file, does it exist?")
        return None


def create_lock_file():
    """
        Write a lock file, incase something is waiting on us to finish
        its more like an indication we're still busy
    """
    if p.exists(LOCK_FILE_NAME):
        return FileExistsError

    open(LOCK_FILE_NAME, 'a').close()
    return None


def release_lock_file():
    """ Removes any lock file held """
    try:
        os.remove(LOCK_FILE_NAME)
        log.debug("Lock file removed")
    except FileNotFoundError:
        log.debug("Could not find lock file to release")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        prog='backup_script.py',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=textwrap.dedent('''\
             Script for backing up a directory

             It will take the config.json file, parse, and tar specified files.
             Ensure all keys are specified, or program will exit.
             '''))
    parser.add_argument('-f', '--full', action='store_true',
                        help='Does a full backup of the directory (otherwise incremental)')
    parser.add_argument('-v', '--verbose', action='store_true', help='Turns on warnings')
    parser.add_argument('-c', '--console_log', action='store_true', help='Log to console only')
    args = parser.parse_args()

    backup_items, script_actions = create_backup_items()

    # Sort out some logging
    log_level = log.INFO
    if args.verbose:
        log_level = log.DEBUG

    if args.console_log:
        log.basicConfig(level=log_level, format='%(asctime)s %(levelname)s: %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S')
        log.info("Script logging to console only")
    else:
        try:
            log.basicConfig(level=log_level, format='%(asctime)s %(levelname)s: %(message)s',
                            datefmt='%Y-%m-%d %H:%M:%S', filename=script_actions.log_file)
        except PermissionError:
            print("ERROR: Cannot write to supplied log location: {}".format(script_actions.log_file))
            # User has to exit, we don't know where to write our logs too.
            quit(0)

    if backup_items is None:
        log.info("No backup jobs found, exiting")
        sys.exit()

    date = t.date.today()
    jobs = []
    threads = []

    ret = create_lock_file()
    if ret is FileExistsError:
        log.error(
            "Backup is still running (delete {0} if this isn't correct)".format(LOCK_FILE_NAME))
        sys.exit()

    script_start_time = timer()

    # Start iterating over the list of items to backup. If the item
    # is not enabled, let the user know, and move onto the next item.
    for item in backup_items:
        if not item.is_enabled():
            log.warning("{0} is not enabled, skipping ".format(item.name))
            continue

        # Queue up the jobs we have to do
        item.queue_items(full_backup=args.full)

        # Append the item to the jobs list.
        jobs.append(item)

    if script_actions.preaction:
        try:
            pre = subprocess.Popen(script_actions.preaction, shell=True)
            pre.wait()
        except FileNotFoundError:
            log.error("Failed to run the pre_action_script command")

    for job in jobs:
        t = threading.Thread(target=job.start)
        threads.append(t)
        t.start()

    for thread in threads:
        thread.join()

    if script_actions.postaction:
        try:
            post = subprocess.Popen(script_actions.postaction, shell=True)
            post.wait()
        except FileNotFoundError:
            log.error("Failed to run the pre_action_script command")

    time_taken = timer() - script_start_time
    time_format = "%M mins %S seconds"
    # If job too longer than 3599 seconds (1 hr), display hours as well
    if time_taken > 3599:
        time_format = "%H hrs %M mins %S seconds"

    elapsed_time = time.strftime(time_format, time.gmtime(time_taken))

    if script_actions.showtime:
        log.info("Backup script took {0} to complete".format(elapsed_time))

    log.info("Script finished")

    # Remove our lock file, we're done.
    release_lock_file()
