"""
The contents of this file are (c) Ian Bicking and MIT-licensed:

 https://bitbucket.org/ianb/devauth/raw/36278dbe285b/devauth/htpasswd.py

Read Apache htpasswd files

``read_groups`` also reads Apache-style group files (which are just
``username: group1 group2``)
"""

class NoSuchUser(Exception):
    """
    Raised by check_password() when no user by that name is found
    """
    pass

# From: http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/325204
def apache_md5crypt(password, salt, magic='$apr1$'):
    """
    Calculates the Apache-style MD5 hash of a password
    """
    # /* The password first, since that is what is most unknown */ /* Then our magic string */ /* Then the raw salt */
    import md5
    m = md5.new()
    m.update(password + magic + salt)

    # /* Then just as many characters of the MD5(pw,salt,pw) */
    mixin = md5.md5(password + salt + password).digest()
    for i in range(0, len(password)):
        m.update(mixin[i % 16])

    # /* Then something really weird... */
    # Also really broken, as far as I can tell.  -m
    i = len(password)
    while i:
        if i & 1:
            m.update('\x00')
        else:
            m.update(password[0])
        i >>= 1

    final = m.digest()

    # /* and now, just to make sure things don't run too fast */
    for i in range(1000):
        m2 = md5.md5()
        if i & 1:
            m2.update(password)
        else:
            m2.update(final)

        if i % 3:
            m2.update(salt)

        if i % 7:
            m2.update(password)

        if i & 1:
            m2.update(final)
        else:
            m2.update(password)

        final = m2.digest()

    # This is the bit that uses to64() in the original code.

    itoa64 = './0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'

    rearranged = ''
    for a, b, c in ((0, 6, 12), (1, 7, 13), (2, 8, 14), (3, 9, 15), (4, 10, 5)):
        v = ord(final[a]) << 16 | ord(final[b]) << 8 | ord(final[c])
        for i in range(4):
            rearranged += itoa64[v & 0x3f]; v >>= 6

    v = ord(final[11])
    for i in range(2):
        rearranged += itoa64[v & 0x3f]; v >>= 6

    return magic + salt + '$' + rearranged

def check_entry_password(username, password, entry_password):
    """
    Checks the username and password against the entry found in the
    htpasswd file
    """
    if entry_password.startswith('$apr1$'):
        salt = entry_password[6:].split('$')[0][:8]
        expected = apache_md5crypt(password, salt)
    elif entry_password.startswith('{SHA}'):
        import sha
        expected = '{SHA}' + sha.new(password).digest().encode('base64').strip()
    else:
        import crypt
        expected = crypt.crypt(password, entry_password)
    return entry_password == expected

def parse_htpasswd(fn, stop_username=None):
    """
    Returns a dictionary of usernames and hashed password entries.  If
    stop_username is given, parsing will be finished as soon as that
    username is encountered.
    """
    f = open(fn, 'rb')
    try:
        entries = {}
        for line in f.readlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if ':' not in line:
                raise ValueError(
                    "Bad line (no :): %r" % line)
            username, entry_password = line.split(':', 1)
            entries[username] = entry_password
            if username == stop_username:
                break
        return entries
    finally:
        f.close()

def has_username(username, htpasswd_fn):
    """
    Returns True/False based on whether the username was found in the
    file.
    """
    entries = parse_htpasswd(htpasswd_fn, username)
    return entries.has_key('username')

def check_password(username, password, htpasswd_fn):
    """
    Returns True or False, or raises NoSuchUser if no user exists
    (False means user exists, but password is incorrect).
    """
    entries = parse_htpasswd(htpasswd_fn, username)
    if not entries.has_key(username):
        raise NoSuchUser('No user: %r' % username)
    return check_entry_password(
        username, password, entries[username])

def read_groups(htgroup_fn, strict=True):
    """
    Returns a dictionary of {group: user_list}

    If ``strict`` is true, then any malformed lines will be rejected.
    The file may always contain empty and comment lines.
    """
    groups = {}
    f = open(htgroup_fn)
    try:
        for line in f.readlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if ':' not in line:
                # Badly formatted line
                if strict:
                    continue
                else:
                    raise ValueError("Bad line: %r" % line)
            group_name, users = line.split(':', 1)
            users = users.strip().split()
            if groups.has_key(group_name):
                if not strict:
                    raise ValueError(
                        "Group shows up twice: %r" % group_name)
                groups[group_name].extend(users)
            else:
                groups[group_name] = users
        return groups
    finally:
        f.close()

def user_groups(username, htgroup_fn, strict=True):
    """
    Returns a list of group names for the given user
    """
    groups = []
    for group_name, users in read_groups(htgroup_fn, strict=strict).items():
        if username in users:
            groups.append(group_name)
    return groups
