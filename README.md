# PIM-DM

We have implemented the specification of PIM-DM ([RFC3973](https://tools.ietf.org/html/rfc3973)).
This repository stores the implementation of this protocol. The implementation is written in Python language and is destined to Linux systems.


# Requirements

 - Linux machine
 - Python3 (we have written all code to be compatible with at least Python v3.2)
-  pip (to install all dependencies)


# Installation
You may need sudo permitions, in order to run this protocol. This is required because we use raw sockets to exchange control messages. For this reason, some sockets to work properly need to have super user permissions.

First clone this repository:
  `git clone https://github.com/pedrofran12/pim_dm.git`

Then enter in the cloned repository and install all dependencies:
   `pip3 install -r requirements.txt`
 
And thats it :D


# Run protocol

In order to interact with the protocol you need to allways execute Run.py file. You can interact with the protocol by executing this file and specifying a command and corresponding arguments:

   `sudo python3 Run.py -COMMAND ARGUMENTS`

In order to determine which commands are available you can call the help command:
	`sudo python3 Run.py -h`
    or
	`sudo python3 Run.py --help`

In order to start the protocol you first need to explicitly start it. This will start a daemon process, which will be running in the background. The command is the following:
	`sudo python3 Run.py -start`

Then you can enable the protocol in specific interfaces. You need to specify which interfaces will have IGMP enabled and which interfaces will have the PIM-DM enabled.
To enable PIM-DM, without State-Refresh, in a given interface, you need to run the following command:
	`sudo python3 Run.py -ai INTERFACE_NAME`

To enable PIM-DM, with State-Refresh, in a given interface, you need to run the following command:
	`sudo python3 Run.py -aisf INTERFACE_NAME`

To enable IGMP in a given interface, you need to run the following command:
	`sudo python3 Run.py -aiigmp INTERFACE_NAME`

If you have previously enabled an interface without State-Refresh and want to enable it, in the same interface, you first need to disable this interface, and the run the command -aisr. The same happens when you want to disable State Refresh in a previously enabled StateRefresh interface.  

To remove a previously added interface, you need run the following commands:
To remove a previously added PIM-DM interface:
	`sudo python3 Run.py -ri INTERFACE_NAME`

To remove a previously added IGMP interface:
	`sudo python3 Run.py -riigmp INTERFACE_NAME`

If you want to stop the protocol process, and stop the daemon process, you need to explicitly run this command:
	`sudo python3 Run.py -stop`



## Commands for monitoring the protocol process
We have built some list commands that can be used to check the "internals" of the implementation.

 - List neighbors: 
	 Verify neighbors that have established a neighborhood relationship
	`sudo python3 Run.py -ln`

 - List state:
    List all state machines and corresponding state of all trees that are being monitored. Also list IGMP state for each group being monitored.
	`sudo python3 Run.py -ls`

 - Multicast Routing Table:
   List Linux Multicast Routing Table (equivalent to ip mroute -show)
	`sudo python3 Run.py -mr`

## Change settings

Files tree/globals.py and igmp/igmp_globals.py store all timer values and some configurations regarding IGMP and the PIM-DM. If you want to tune the implementation, you can change the values of these files. These configurations are used by all interfaces, meaning that there is no tuning per interface.
