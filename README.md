# backup_script
A simple(ish) script that creates tar files of directories listed in a config.json file.

```python3 backup_script.py -h``` for help

To run, just pop this in a directory of your choice, edit the config.json file including the directories that you wish to tar up 

```python3 backup_script.py -f``` will create a full backup (including snar file) at location ... dest_path/name/full-name-YYYY-MM-DD.tar.gz

Once that is done, running ```python3 backup_script.py``` will create an incremental backup in the same location, using the snar file there.  


Since backup_script.py spins each backup into its own thread, it creates a lock file in its working directory that is deleted when all processes are finished. This is so anything waiting on the completion of backup_script.py can be sure nothing else is running, or even to stop backup_script.py from spinning up more threads trying to write the same tar files.

## Options for backup_script: ##
Show the overall script time at the end, show_script_time: [type bool] true/false   
Execute command before script runs, pre_script_action: [type string] command    
Execute command after script runs, post_script_action: [type string] command

Item options      
Name of item, `name: [type string] string`    
Where you want to tar from, `src_path: [type string] path/to/source`   
Where your tar should be put, `dest_path: [type string] path/to/destination`   
Enable or disable this item, `enabled: [type bool] true/false`   
Does an action before tar is started, `pre_action: [type string] command`   
Does an action after tar is finished, `post_action: [type string] command`   
Any extra options for the tar process, `tar_opts: [type string] options`   
Show how long the item took to process, `show_time_taken: [type bool] true/false`
