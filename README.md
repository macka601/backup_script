# backup_script
A simple(ish) script that creates tar files of directories listed in a config.json file.

```python3 backup_script.py -h``` for help

To run, just pop this in a directory of your choice, edit the config.json file including the directories that you wish to tar up 

```python3 backup_script.py -f``` will create a full backup (including snar file) at location ... dest_path/name/full-name-YYYY-MM-DD.tar.gz

Once that is done, running ```python3 backup_script.py``` will create an incremental backup in the same location, using the snar file there.  


Since backup_script.py spins each backup into its own thread, it creates a lock file in its working directory that is deleted when all processes are finished. This is so anything waiting on the completion of backup_script.py can be sure nothing else is running, or even to stop backup_script.py from spinning up more threads trying to write the same tar files.
