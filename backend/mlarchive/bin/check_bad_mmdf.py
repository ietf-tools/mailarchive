#!../../../env/bin/python

'''
Some legacy mbox files in the archive start out in one format,
MMDF (https://www.neomutt.org/man/mmdf) but change to mbox style
mid-file.  See ietf list.  This script will identify such files.

./check_bad_mmdf [dir]
'''


import os
import sys


def is_old_mbox(fp):
    line = fp.readline()
    if line == '\x01\x01\x01\x01\n':
        return True
    else:
        return False


def main():
    d = sys.argv[1]
    root = os.path.dirname(d)
    files = [os.path.join(d, f) for f in os.listdir(d)]
    files = [item for item in files if not os.path.isdir(item)]

    for file in files:
        with open(file) as f:
            if not is_old_mbox(f):
                continue
            while True:
                line = f.readline()
                if line == '\x01\x01\x01\x01\n':
                    line = f.readline()
                    if line and not line == '\x01\x01\x01\x01\n':
                        print("{}:{},{}".format(file, f.tell(), line))
                elif line == '':
                    break


if __name__ == "__main__":
    main()
