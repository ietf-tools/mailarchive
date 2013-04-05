#!/usr/bin/python

# MLABAST Message archiving engine
# 
# This program runs from the command line, and accepts a set of switches and an
# argument.  The argumment can be a directory, a file containing a single message, an
# mbox mail archive file, or a single message as a string
# 
# In addition to switches specifying the input type, there are also a verbose reporting 
# option to display detailed information to the console during the import process.
# 
# System configuration is in the config.py file

# Import Modules
import sys
import datetime
import time
import re
import os
import mailbox
import email
import MySQLdb
import hashlib
import base64
import config
import _classes as mlabast_classes

# Define Local Functions

def load_message(mlabast, listname, message_string):
    import config
        
    config = config.MLABAST_config()
    
    # Load the email message into the library parser
    try:
        msg = email.message_from_string(message_string)
    except:
        if not mlabast.silent:
            print"""Error parsing message"""
            if mlabast.verbose:
                print message_string
                

    # Instantiate a mailing list object, and call the load or create method to 
    # either load or create the mailing list record as appropriate.
    
    mlist = mlabast_classes.maillist()
    mlist.load_or_create_list(mlabast,listname)
    
    # At this point, the mlist object has been populated from the database, either
    # from an existing or newly created mailing list record.  It is time to create the 
    # message record in the archive_message table
    
    # Create the message object, and assign it's list_id to the id of the list we just
    # created or retrieved.  Then pass it to the mail_message's create method
    
    mail_message = mlabast_classes.mailmessage()
    mail_message.email_list_id = mlist.id
    mail_message.create_from_maillib(mlabast, msg, listname)

def load_message_from_file(mlabast, listname, filename):

    # Loading a single message from a file
    # In this case, we are actualy just building a big string
    # and then we will pass it to the load_message method
    
    f = open(filename, "r")
    message_string = f.read()
    f.close()
    load_message(mlabast, listname, message_string)

################
## Dispatcher ##
################

if __name__ == '__main__':
    # instantiate the superclass 
    mlabast = mlabast_classes.mlabast()
    
    # Initialize variables
    import_mode = ""
    mlabast.silent = False
    mlabast.verbose = False
    
    # Get arguments
    try:
        switches = sys.argv[1]
        listname = sys.argv[2]
    except:
        print"""\n\nError: incomplete command.\nPlease invoke in the form <command> <switches> <listname> <filename>\n\n"""
        exit()
    
    try:
        message_argument = sys.argv[3]
    except:
        message_argument = ""
        
    # parse the switches
    
    # Supported switches:
    #
    # -a : Archive - a mbox format mailbox archive
    # -f : File - a text file containing a single email messsage
    # -m : Message - the argment is a complete message as a string
    # -p : Pipe - process stdin as a message
    # -s : Return no output to the console (default)
    # -v : Verbose - output detailed information during the archiving process
    
    # Test for incompatible switches
    
    if switches.find("a") > -1 and switches.find("f") > -1:
        print "Only one import mode may be specified."
        exit()
        
    if switches.find("a") > -1 and switches.find("m") > -1:
        print "Only one import mode may be specified."
        exit()
    
    if switches.find("m") > -1 and switches.find("f") > -1:
        print "Only one import mode may be specified."
        exit()
        
    if switches.find("p") > -1 and switches.find("f") > -1:
        print "Only one import mode may be specified."
        exit()
        
    if switches.find("p") > -1 and switches.find("m") > -1:
        print "Only one import mode may be specified."
        exit()
    
    if switches.find("p") > -1 and switches.find("a") > -1:
        print "Only one import mode may be specified."
        exit()
        
    if switches.find("s") > -1 and switches.find("v") > -1:
        print "Reporting cannot be both silent and verbose."
        exit()
    
    # Switching is compatible, parse switches
    
    for i in range (0,len(switches)):
        if switches[i] == "a":
            import_mode = "a"
        elif switches[i] == "f":
            import_mode = "f"
        elif switches[i] == "m":
            import_mode = "m"
        elif switches[i] == "p":
            import_mode = "p"
        elif switches[i] == "s":
            mlabast.silent = True
        elif switches[i] == "v":
            mlabast.verbose = True
            
        
    # Report switches and argument if mode is verbose
    
    if mlabast.verbose:
        print"""\n\nInitiating run.\nImport mode = %s\nMessage argument = %s\n\n""" % (import_mode, message_argument)
        
        
    # Process a single file
    
    if import_mode == "f":
        mlabast.startclock()
        ## test to see if the file exists
        count = 1
        if (os.path.exists(message_argument)):
            load_message_from_file(mlabast,listname, message_argument)
        else:
            print"""Unable to load message from %s""" % message_argument
            mlabast.errorcount = mlabast.errorcount+1
            
        mlabast.stopclock()
            
    if import_mode == "p":
        mlabast.startclock()
        ## importing from the stdin
        message_string = ""
        data = sys.stdin.readlines()
        msg = ""
        for line in data:
            message_string = message_string + line
        
        load_message(mlabast, listname, message_string)
        
        mlabast.stopclock()
        
    if import_mode == "a":
        count = 0
        mlabast.startclock()
        ## This is an mbox archive
        ## test to see if the file exists
        if (os.path.exists(message_argument)):
            ## try to load the mbox:
            try:
                mbox = mailbox.mbox(message_argument)
            except:
                print"""Error: unable to parse mbox archive in %s""" % message_argument
                exit()
            # we have opened the mbox, so walk through it, pull each message as a string
            # and feed it to the processor
            
            for msg in mbox:
                load_message(mlabast, listname, msg.as_string())
                count = count + 1
                
        else:
            print"""Error: unable to open %s""" % message_argument
            mlabast.errorcount = mlabast.errorcount+1
        mlabast.stopclock()
    
    if not mlabast.silent:
        print"""%i messages examined in %2.2f seconds""" %(count, mlabast.elapsedtime())
        print"""%i errors encountered""" % mlabast.errorcount
        print"""%i hash errors encountered""" % mlabast.hasherrorcount
