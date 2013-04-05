class MLABAST_config(object):                             
	def __init__(self):                                   
		"""This is the configuration class for the MLABAST Message Archive Tool"""
		
		self.archive_directory="/a/home/rcross/data/mlabast/"
		self.list_directory = "/a/home/rcross/data/mlabast/mlabast-data/messages/"
		self.attachment_directory = "/a/home/rcross/data//mlabast/mlabast-data/attachments/"
		self.error_directory = "/a/home/rcross/data/mlabast/mlabast-data/errors/"
		self.db = "rc_archive"
		self.db_host = "localhost"
		self.db_user = "rcross"
		self.db_password = "sounders43"
