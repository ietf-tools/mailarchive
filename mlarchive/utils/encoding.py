DEFAULT_CHARSET = 'latin1'

def decode_safely(data, charset=DEFAULT_CHARSET):
    """Return data decoded according to charset, but do so safely."""
    try:
        return unicode(data,charset or DEFAULT_CHARSET)
    except (UnicodeDecodeError, LookupError) as error:
        # logger.warning("Decode Error [{0}]".format(error.args))
        return unicode(data,DEFAULT_CHARSET,errors='replace')

