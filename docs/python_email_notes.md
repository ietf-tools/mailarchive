# Dec 7, 2022: Some notes on Python email package use

## Summary

The maintainer of the Python email package, R. David Murray, implemented a major upgrade to the package, known internally as email6, which was rolled out in Python 3.3 and 3.4. This upgrade introduced, among other things, a new improved data model, email.message.EmailMessage. This model uses string-like smart objects to store header data, compared to regular string objects in the legacy model.

### What determines the model you are using?

Mail Archive uses the email parsing convenience functions, message_from_bytes and message_from_binary_file, to convert byte streams to an email object. Take email.message_from_bytes for example. If you use policy=policy.compat32 the function returns a legacy email.messasge.Message object. If you use any other policy, eg. SMTP, the function returns a email.message.EmailMessage object. Mail Archive was using the legacy compat32 policy.

### Issue https://github.com/ietf-tools/mailarch/issues/3515

In July 2022, it was discovered some messages encoded as base64 were not being decoded for display properly. It turns out the Content-Transfer-Encoding (CTE) value contained trailing whitespace, "base64 ", causing the email package decoding functions to fail. The solution was to use the "new" policy framework to allow subclassing the CTE header parsing and strip the trailing whitespace, restoring proper decoding. 
https://github.com/ietf-tools/mailarch/commit/c8e7e730f74b941dce0aefa843122f6c83ac2859

However there were side effects. The new EmailMessage performs more involved parsing of header values to support smarter header objects. This results in more unrecoverable errors parsing malformed headers, compared to the legacy Message model. A full scan of the archive revealed 300+ messages with such headers (I expected more). These can be divided into 6 classes of problems which utlimately should be addressed as cPython bugs.

For now I have created wrappers for the parsing convenience functions that try and use the modern policy first and fall back to the compat32 policy if that fails.

## References

### Python Documentation

https://docs.python.org/3/library/email.html#module-email
https://docs.python.org/3/whatsnew/3.3.html#email
https://docs.python.org/3/whatsnew/3.4.html#email

### R. David Murray commentary on email6

http://www.bitdance.com/blog/
https://pyvideo.org/pycon-us-2012/the-email-package-past-present-and-future.html

