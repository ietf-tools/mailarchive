from django.conf import settings
from django.core.management.base import CommandError
from email.utils import parsedate, parsedate_tz, mktime_tz
from mlarchive.archive.models import *
from tzparse import tzparse

import base64
import datetime
import hashlib
import mailbox
import os
import pytz
import re
import time

from django.utils.log import getLogger
logger = getLogger('mlarchive.custom')

class ListError(Exception):
    pass
    
class GenericWarning(Exception):
    pass
    
class DateError(Exception):
    pass
    
class loader(object):
    def __init__(self, filename, **options):
        self.endtime = 0
        self.filename = filename
        self.options = options
        self.starttime = 0
        self.stats = {'irts': 0,'mirts': 0,'count': 0, 'errors': 0}
        self.listname = options.get('listname')
        # init mailbox iterator
        if self.options.get('format') == 'mmdf':
            self.mb = mailbox.MMDF(filename)
        else:
            self.mb = mailbox.mbox(filename)   # TODO: handle different types of input files
        
        if not self.listname:
            self.listname = self.guess_list()
        
        if not self.listname:
            raise ListError
            
        logger.info('loader called with: %s' % self.filename)
        
        # TODO: handle private
        self.email_list,created = EmailList.objects.get_or_create(name=self.listname,defaults={'description':self.listname})
        
    def elapsedtime(self):
        return self.endtime - self.starttime
        
    def fix_date(self, datestring):
        '''
        Call this function with a date that can't be parsed by parsedate.  It takes a string and
        returns a naive datetime object that represents the UTC time.
        '''
        # EXAMPLE: Wed 23 Sep 92 00:15:15-PDT
        date_formats = ["%a %d %b %y %H:%M:%S-%Z",
                        "%d %b %Y %H:%M-%Z",
                        "%a %b %d %H:%M:%S %Y",
                        "%a %b %d %H:%M:%S %Y %Z",
                        "%a, %d %b %Y %H:%M:%S %Z"]
        
        for format in date_formats:
            try:
                dt = tzparse(datestring,format)
                break
            except ValueError:
                pass
        dt_in_utc = dt.astimezone(pytz.utc)
        dt_naive = dt_in_utc.replace(tzinfo=None)
        return dt_naive
        
        #p = re.compile(r'.*\d{2}:\d{2}:\d{2}\-(PDT|PST|\d{4})')
        #if p.match(date):
        #    new_date = date.replace('-',' ')
        #    pdate = parsedate_tz(new_date)
        #    if pdate:
        #        return pdate
        
    def get_date(self,msg):
        '''
        Gets the Date from the message headers.  Check for Date field which is supposed to be
        the date and time the user sent the message.  Sometimes this field is empty or even
        absent.  In this case get the date from the intial "From" line.  This is the date and
        time the message was recieved by the list server.  Returns a naive Datetime object in UTC
        time to simplify sorting.
        '''
        date = msg.get('date')
        if date:            
            # Convert RFC2822 datestring to UTC
            pdate = parsedate_tz(date)
            if pdate:
                utc = mktime_tz(pdate)
                utcdate = datetime.datetime.utcfromtimestamp(utc)
            else:
                utcdate = self.fix_date(date)
            if not utcdate:
                raise DateError("Can't parsedate: %s" % date)
            return utcdate
        else:
            # expect line like "From [email] RFC2822 date", no time zone info
            line = msg.get_from()
            if '@' in line:
                # mhonarc archive
                date_parts = line.split()[1:]
            else:
                # pipermail archive
                date_parts = line.split()[3:]
            tuple = parsedate(' '.join(date_parts))
            stamp = time.mktime(tuple)
            utcdate = datetime.datetime.utcfromtimestamp(stamp)
            return utcdate
            
    def get_hash(self,msgid):
        '''
        Takes the name of the email list and msgid and returns the hashcode
        '''
        sha = hashlib.sha1(msgid)
        sha.update(self.listname)
        return base64.urlsafe_b64encode(sha.digest())
        
    def get_stats(self):
        '''
        Return statistics from the process() function
        '''
        return "%s:%s:%s:%s:%.3f\n" % (self.listname,os.path.basename(self.filename),
                                     self.stats['count'],self.stats['errors'],self.elapsedtime())
    def get_thread(self,msg):
        '''
        This is a very basic thread algorithm.  If 'In-Reply-To-' is set, look up that message 
        and return it's thread id, otherwise return a new thread id.  This is crude for many reasons.
        ie. what if the referenced message isn't loaded yet?  We load message files in date order
        to minimize this.
        '''
        irt = msg.get('In-Reply-To','').strip('<>')
        if irt:
            self.stats['irts'] += 1
            try:
                irt_msg = Message.objects.get(msgid=irt)
                thread = irt_msg.thread
            except (Message.DoesNotExist, Message.MultipleObjectsReturned):
                self.stats['mirts'] += 1
                thread = Thread.objects.create()
        else:
            thread = Thread.objects.create()
        return thread
    
    def guess_list(self):
        '''
        Helper function to determine the list we are importing based on header values
        '''
        # not enought info in MMDF-style mailbox to guess list
        if isinstance(self.mb,mailbox.MMDF):
            return None
            
        if len(self.mb) == 0:
            return None
            
        msg = self.mb[0]
        if msg.get('X-BeenThere'):
            val = msg.get('X-BeenThere').split('@')[0]
            if val:
                return val
        if msg.get('List-Post'):
            val = msg.get('List-Post')
            match = re.match(r'<mailto:(.*)@.*',val)
            if match:
                return match.groups()[0]
        
    def load_message(self,m):
        '''
        This function takes an email.Message object and creates the archive.Message object
        '''
        self.stats['count'] += 1
        msgid = handle_header(m.get('Message-ID',''))
        if msgid:
            msgid = msgid.strip('<>')
        else:
            # see if this is a resent Message, which sometimes have missing Message-ID field
            resent_msgid = m.get('Resent-Message-ID')
            if resent_msgid:
                msgid = resent_msgid.strip('<>')
        if not msgid:
            raise GenericWarning('No MessageID (%s)' % m.get_from())
            
        inrt = m.get('In-Reply-To','')
        if inrt:
            inrt = inrt.strip('<>')
            
        hashcode = self.get_hash(msgid)
        
        # check for duplicate message id, and skip
        if Message.objects.filter(msgid=msgid,email_list=self.email_list):
            raise GenericWarning('Duplicate msgid: %s' % msgid)
            
        # check for duplicate hash
        if Message.objects.filter(hashcode=hashcode):
            raise CommandError('Duplicate hash, msgid: %s' % msgid)
            
        msg = Message(date=self.get_date(m),
                      email_list=self.email_list,
                      frm = handle_header(m.get('From','')),
                      hashcode=hashcode,
                      inrt=inrt,
                      msgid=msgid,
                      subject=handle_header(m.get('Subject','')),
                      thread=self.get_thread(m),
                      to=handle_header(m.get('To','')))
        msg.save()
        
        # save disk object
        if not self.options.get('test'):
            path = os.path.join(settings.ARCHIVE_DIR,self.email_list.name,hashcode)
            if not os.path.exists(os.path.dirname(path)):
                os.mkdir(os.path.dirname(path))
            with open(path,'w') as f:
                f.write(m.as_string())
        
    def process(self):
        for m in self.mb:
            try:
                self.load_message(m)
            except GenericWarning as e:
                logger.warn("Import Warn [{0}, {1}, {2}]".format(self.filename,e.args,m.get_from()))
            except Exception as e:
                logger.error("Import Error [{0}, {1}, {2}]".format(self.filename,e.args,m.get_from()))
                self.stats['errors'] += 1
        self.mb.close()
        
    def startclock(self):
        self.starttime = time.time()
        
    def stopclock(self):
        self.endtime = time.time()
        
class mlabast(object):
    def __init__(self):
        """This is the control class for the MLABAST Message Archive Tool"""
        import time
        
        ## Reporting mode
        self.silent = False
        self.verbose = False
        self.starttime = 0
        self.endtime = 0
        self.errorlist = ""
        self.errorcount = 0
        self.hasherrorcount=0
        self.parseerror=0
    
    def startclock(self):
        self.starttime = time.time()
        
    def stopclock(self):
        self.endtime = time.time()
        
    def elapsedtime(self):
        return self.endtime - self.starttime
    
    
class mailmessage(object):                             
    def __init__(self):                                   
        """This is the mailmessage class MLABAST Message Archive Tool"""
        
        # The archive_message schema:
        # +---------------+--------------+------+-----+---------+----------------+
        # | Field         | Type         | Null | Key | Default | Extra          |
        # +---------------+--------------+------+-----+---------+----------------+
        # | id            | int(11)      | NO   | PRI | NULL    | auto_increment |
        # | cc            | varchar(255) | NO   |     | NULL    |                |
        # | date          | datetime     | NO   | MUL | NULL    |                |
        # | email_list_id | int(11)      | NO   | MUL | NULL    |                |
        # | frm           | varchar(255) | NO   | MUL | NULL    |                |
        # | hashcode      | varchar(28)  | NO   | MUL | NULL    |                |
        # | headers       | longtext     | NO   |     | NULL    |                |
        # | inrt          | varchar(255) | NO   |     | NULL    |                |
        # | legacy_number | int(11)      | YES  | MUL | NULL    |                |
        # | msgid         | varchar(255) | NO   | MUL | NULL    |                |
        # | subject       | varchar(255) | NO   |     | NULL    |                |
        # | thread_id     | int(11)      | NO   | MUL | NULL    |                |
        # | to            | varchar(255) | NO   |     | NULL    |                |
        # +---------------+--------------+------+-----+---------+----------------+
        
        self.id = 0
        self.cc = ""
        self.date = ""
        self.email_list_id = 0
        self.frm = ""
        self.hashcode = ""
        self.headers = ""
        self.inrt = ""
        self.legacynumber = 0
        self.msgid = ""
        self.subject = ""
        self.thread_id = 0
        self.to = ""
        self.body = ""
        
    def make_hash(self, listname):
        import hashlib
        import base64
        import time
        
        # make a hash from the message id and the name of the list
        try:
            id_hash = hashlib.sha1(self.msgid)
            id_hash.update(listname)
        except:
            return "0"
        return base64.urlsafe_b64encode(id_hash.digest())
        
    def create_from_maillib(self, mlabast, msg, listname):
        import MySQLdb
        import config
        import time
        import _classes as mlabast_classes
                
        config = config.MLABAST_config()
        newthread = mlabast_classes.archive_thread()
    
        # Suppress database warnings
        from warnings import filterwarnings
        filterwarnings('ignore', category = MySQLdb.Warning)    
        
        # populate method properties from the msg fields
        self.cc = msg.get("Cc")
        self.date = msg.get("Date") 
        self.frm = msg.get("From")
        self.headers = "\n".join(["%s: %s" % (k, v) for k, v in msg.items()])
        self.inrt = msg.get("In-Reply-To")
        self.msgid = msg.get("Message-Id")
        self.subject = msg.get("Subject")
        self.to = msg.get("To")
        self.body = msg.get_payload()
    
         # Check for a valid message
        if not (self.msgid):
            mlabast.errorcount = mlabast.errorcount + 1
            print"""Invalid ID"""
            return

        # Escape each string for writing to db
        cleaned_cc = ""
        cleaned_frm = ""
        cleaned_headers = ""
        cleaned_inrt = ""
        cleaned_msgid = ""
        cleaned_subject = ""
        cleaned_to = ""
        
        if self.cc:
            cleaned_cc = MySQLdb.escape_string(self.cc)
        if self.frm:
            cleaned_frm = MySQLdb.escape_string(self.frm)
        if self.headers:
            cleaned_headers = MySQLdb.escape_string(self.headers)
        if self.inrt:
            cleaned_inrt = MySQLdb.escape_string(self.inrt)
        if self.msgid:
            cleaned_msgid = MySQLdb.escape_string(self.msgid)
        if self.subject:
            cleaned_subject = MySQLdb.escape_string(self.subject)
        if self.to:
            cleaned_to = MySQLdb.escape_string(self.to)
        
        # Generate a hashcode for the message
        self.hashcode = self.make_hash(listname)
        if self.hashcode == "0":
            mlabast.errorcount = mlabast.errorcount + 1
            return
    
        # Reformat the date
        # The RFC standard date format is like this:
        # Fri, 12 Oct 2007 12:19:35 +0200
        # 
        # Convert to a datetime object and then get the SQL format from it
        try:
            splittime = self.date.split(" ")
            newdate = splittime[1] + " " + splittime[2] + " " + splittime[3] + " " + splittime[4]
            parseddate = time.strptime(newdate,"%d %b %Y %H:%M:%S")
            sql_date = time.strftime("%Y-%m-%d %H:%M:%S", parseddate)
        except:
            sql_date = ""
            mlabast.errorcount = mlabast.errorcount + 1
            
            # Create the file for the message and write it out
            message_file = config.error_directory+"%s/%s" % (listname,self.hashcode)
            f = open(message_file,"w")
            f.write(self.headers)
            f.write("\n\n")
            try:
                f.write(self.body)
            except:
                for part in msg.walk():
                    if part.get_content_type() == 'text/plain':
                        f.write(part.get_payload())
            f.close()
        
        # Determine thread ID
        #
        # If a message has no In-Reply-To field, consider it a new thread, and create a thread_id for items
        
        if not self.inrt:
            self.thread_id = newthread.makethread()
        else:
            # Message has an In-Reply-To, so we need to look and see if we have the message it replied to, or another reply to it
            db = MySQLdb.connect(host=config.db_host, user=config.db_user, passwd=config.db_password, db=config.db)
            query = """select thread_id from archive_message where msgid = "%s" """ % (cleaned_inrt)
            cursor = db.cursor()
            # execute SQL statement
            cursor.execute(query)

            # get the number of rows in the resultset
            numrows = int(cursor.rowcount)
            if numrows > 0:
                # We found a match, extract the thread_id
                for x in range(0,numrows):
                    row = cursor.fetchone()
                    self.thread_id = row[0]
            else:
                # We did not find a match, so this is a new thread for us
                self.thread_id = newthread.makethread()
            
            cursor.close()
              
              
        if mlabast.verbose:
            print"""Processing %s""" % self.hashcode    
        # Check for a hash collision
        db = MySQLdb.connect(host=config.db_host, user=config.db_user, passwd=config.db_password, db=config.db)
        query = """select * from archive_message where hashcode = "%s" """ % self.hashcode
        
        # create a cursor
        cursor = db.cursor()
        
        # execute SQL statement
        cursor.execute(query)
        
        # get the number of rows in the resultset
        numrows = int(cursor.rowcount)
  
        if numrows == 0:
            # There is no message with this hashcode, so create the record
            # lock this list for inserts
            
            query = """insert into archive_message values (0,"%s","%s",%s,"%s","%s","%s","%s",%s,"%s","%s",%s,"%s")""" % (cleaned_cc, sql_date, self.email_list_id, cleaned_frm , self.hashcode, cleaned_headers, cleaned_inrt, self.legacynumber, cleaned_msgid, cleaned_subject, self.thread_id, cleaned_to)
            cursor.execute(query)
            thismessageid = cursor.lastrowid

        else:
            mlabast.hasherrorcount = mlabast.hasherrorcount + 1
            if not mlabast.silent:
                print"""Hash collision detected on hash %s""" % self.hashcode
                print self.msgid
                if mlabast.verbose:
                    row = cursor.fetchone()
                    print row[9]
                    if (self.msgid != row[9]):
                        print"""*** MISMATCH ***"""
                    print"""\n\n"""    
        cursor.close
        

        # Create the file for the message and write it out
        try:
            message_file = config.list_directory+"%s/%s" % (listname,self.hashcode)
            f = open(message_file,"w")
            try:
                f.write(self.body)
            except:
                for part in msg.walk():
                    if part.get_content_type() == 'text/plain':
                        f.write(part.get_payload()) 
            f.close()
        except:
            mlabast.errorcount = mlabast.errorcount + 1
        
        ## Write the references
        
        if msg.get("References"):
            references = msg.get("References").split("\n\t")
            db = MySQLdb.connect(host=config.db_host, user=config.db_user, passwd=config.db_password, db=config.db)
            cursor = db.cursor()
            referenceorder=0
            for ref in references:
                ref = ref.replace("\t","")
                query = """select id from archive_message where msgid = "%s" """ % ref
                try:
                    cursor.execute(query)
                except:
                    continue

                numrows = int(cursor.rowcount)
                if numrows > 0:
                    # We found a match, extract the message id
                    for x in range(0,numrows):
                        row = cursor.fetchone()
                        refid = row[0]
                  
                    try:
                        query = """insert into archive_reference values (0,%i,%i,%i)""" % (thismessageid, refid, referenceorder)
                        cursor.execute(query)
                        referenceorder = referenceorder+1
                    except:
                        continue 
            cursor.close()
              
    def throw_lock_file(self, config):
        import time
        import os
        
        ## if a lock file exists, wait for it to clear
        lockfilepath = "%slockfiles/%s_messagecreate" % (config.archive_directory, self.email_list_id)
        while os.path.exists(lockfilepath):
            time.sleep(3)
        
        ## lock file is gone, create one
        f = open (lockfilepath,"w")
        
        return True
        
    def remove_lock_file(self, config):
        import time
        import os
        
        lockfilepath = "%slockfiles/%smessagecreate" % (config.archive_directory, self.email_list_id)
        if os.path.exists(lockfilepath):
            os.remove(lockfilepath)
            return True    
        else:
             return False
             
class archive_thread(object):                             
    def __init__(self):                                   
        """This is the thread class MLABAST Message Archive Tool"""
        
        # The archive_thread schema:
        # +---------------+--------------+------+-----+---------+----------------+
        # | Field         | Type         | Null | Key | Default | Extra          |
        # +---------------+--------------+------+-----+---------+----------------+
        # | id            | int(11)      | NO   | PRI | NULL    | auto_increment |
        # +---------------+--------------+------+-----+---------+----------------+
        
        self.id = 0

        
    def makethread(self):
        # Create a new thread.  Throw a lock file, do an insert, get the last ID and 
        # return it to the caller
        
        import MySQLdb
        import config
        
        config = config.MLABAST_config()
        
        db = MySQLdb.connect(host=config.db_host, user=config.db_user, passwd=config.db_password, db=config.db)
        query = """insert into archive_thread values (0)"""
        
        cursor = db.cursor()
          
        # execute SQL statement
        clear = self.throw_lock_file(config)
        cursor.execute(query)
        done = self.remove_lock_file(config)
        
        # get the last insert id
        
        thread_id = cursor.lastrowid
        
        return thread_id
        
        
    def throw_lock_file(self, config):
        import time
        import os
        
        ## if a lock file exists, wait for it to clear
        lockfilepath = "%slockfiles/threadcreate" % (config.archive_directory)
        while os.path.exists(lockfilepath):
            time.sleep(3)
        
        ## lock file is gone, create one
        f = open (lockfilepath,"w")
        
        return True
        
    def remove_lock_file(self, config):
        import time
        import os
        
        lockfilepath = "%slockfiles/threadcreate" % (config.archive_directory)
        if os.path.exists(lockfilepath):
            os.remove(lockfilepath)
            return True    
        else:
             return False
             
class maillist(object):                             
    def __init__(self):                                   
        """This is the maillist class MLABAST Message Archive Tool"""
        
        # The archive_emaillist schema:
        # +--------------+--------------+------+-----+---------+----------------+
        # | Field        | Type         | Null | Key | Default | Extra          |
        # +--------------+--------------+------+-----+---------+----------------+
        # | id           | int(11)      | NO   | PRI | NULL    | auto_increment |
        # | active       | tinyint(1)   | NO   | MUL | NULL    |                |
        # | date_created | datetime     | NO   |     | NULL    |                |
        # | description  | varchar(255) | NO   |     | NULL    |                |
        # | name         | varchar(255) | NO   | MUL | NULL    |                |
        # | private      | tinyint(1)   | NO   | MUL | NULL    |                |
        # | alias        | varchar(255) | NO   |     | NULL    |                |
        # +--------------+--------------+------+-----+---------+----------------+
        
        self.id = 0
        self.active = 0
        self.datecreated = ""
        self.description = ""
        self.name = ""
        self.private = 0
        self.alias = ""
    
    def throw_lock_file(self, config):
        import time
        import os
        
        ## if a lock file exists, wait for it to clear
        lockfilepath = "%slockfiles/listcreate" % config.archive_directory
        while os.path.exists(lockfilepath):
            time.sleep(3)
        
        ## lock file is gone, create one
        f = open (lockfilepath,"w")
        
        return True
        
    def remove_lock_file(self, config):
        import time
        import os
        
        lockfilepath = "%slockfiles/listcreate" % config.archive_directory
        if os.path.exists(lockfilepath):
            os.remove(lockfilepath)
            return True    
        else:
            return False
             
    def load_or_create_list(self, mlabast, listname):
        import MySQLdb
        import config
        import os
        
        config = config.MLABAST_config()
        
        db = MySQLdb.connect(host=config.db_host, user=config.db_user, passwd=config.db_password, db=config.db)
        listname = MySQLdb.escape_string(listname)
        query = """select * from archive_emaillist where name = "%s" """ % listname
        # create a cursor
        cursor = db.cursor()
          
        # execute SQL statement
        cursor.execute(query)
          
        # get the number of rows in the resultset
        numrows = int(cursor.rowcount)
  
        if numrows == 0:
            # There is no mailing list by this name.  Create the record:
              
            clear = self.throw_lock_file(config)
            query = """Insert into archive_emaillist values (0,1,now(),"%s","%s",0,"")""" % (listname, listname)
            cursor.execute(query)
            removed = self.remove_lock_file(config)
              
            # Since this is a new list, we need to make a directory for it.
            maillist_directory = config.list_directory + "%s/" % listname
              
            if not os.path.exists(maillist_directory):
                os.makedirs(maillist_directory)
          
        cursor.close()
          
        # Either the list existed, or we just created it.  So load it and go home.
        self.loadlist(listname)
          
    def loadlist(self, listname):
        import MySQLdb
        import config
        
        config = config.MLABAST_config()
        
        # Load the list from the database
        db = MySQLdb.connect(host=config.db_host, user=config.db_user, passwd=config.db_password, db=config.db)
        
        query = """select * from archive_emaillist where name = "%s" """ % listname
        # create a cursor
        cursor = db.cursor()
          
        # execute SQL statement
        cursor.execute(query)
          
        # get the number of rows in the resultset
        numrows = int(cursor.rowcount)
  
        for x in range(0,numrows):
            row = cursor.fetchone()
            self.id = row[0]
            self.active = row[1]
            self.datecreated = row[2]
            self.description = row[3]
            self.name = row[4]
            self.private = row[5]
            self.alias = row[6]
              
        cursor.close()

