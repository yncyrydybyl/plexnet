import os
import resource

from test.test_support import TESTFN, unlink

# This test is checking a few specific problem spots.  RLIMIT_FSIZE
# should be RLIM_INFINITY, which will be a really big number on a
# platform with large file support.  On these platforms, we need to
# test that the get/setrlimit functions properly convert the number to
# a C long long and that the conversion doesn't raise an error.

try:
    cur, max = resource.getrlimit(resource.RLIMIT_FSIZE)
except AttributeError:
    pass
else:
    print resource.RLIM_INFINITY == max
    resource.setrlimit(resource.RLIMIT_FSIZE, (cur, max))

# Now check to see what happens when the RLIMIT_FSIZE is small.  Some
# versions of Python were terminated by an uncaught SIGXFSZ, but
# pythonrun.c has been fixed to ignore that exception.  If so, the
# write() should return EFBIG when the limit is exceeded.

# At least one platform has an unlimited RLIMIT_FSIZE and attempts to
# change it raise ValueError instead.

try:
    try:
        resource.setrlimit(resource.RLIMIT_FSIZE, (1024, max))
        limit_set = 1
    except ValueError:
        limit_set = 0
    f = open(TESTFN, "wb")
    try:
        f.write("X" * 1024)
        try:
            f.write("Y")
            f.flush()
            # On some systems (e.g., Ubuntu on hppa) the flush()
            # doesn't always cause the exception, but the close()
            # does eventually.  Try flushing several times in
            # an attempt to ensure the file is really synced and
            # the exception raised.
            for i in range(5):
                time.sleep(.1)
                f.flush()
        except IOError:
            if not limit_set:
                raise
        if limit_set:
            # Close will attempt to flush the byte we wrote
            # Restore limit first to avoid getting a spurious error
            resource.setrlimit(resource.RLIMIT_FSIZE, (cur, max))
    finally:
        f.close()
finally:
    if limit_set:
        resource.setrlimit(resource.RLIMIT_FSIZE, (cur, max))
    unlink(TESTFN)

# And be sure that setrlimit is checking for really large values
too_big = 10L**50
try:
    resource.setrlimit(resource.RLIMIT_FSIZE, (too_big, max))
except (OverflowError, ValueError):
    pass
try:
    resource.setrlimit(resource.RLIMIT_FSIZE, (max, too_big))
except (OverflowError, ValueError):
    pass
