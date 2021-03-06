import py
import sys, stat, os
from pypy.translator.sandbox.vfs import *
from pypy.tool.udir import udir

HASLINK = hasattr(os, 'symlink')

def setup_module(mod):
    d = udir.ensure('test_vfs', dir=1)
    d.join('file1').write('somedata1')
    d.join('file2').write('somelongerdata2')
    os.chmod(str(d.join('file2')), stat.S_IWUSR)     # unreadable
    d.join('.hidden').write('secret')
    d.ensure('subdir1', dir=1).join('subfile1').write('spam')
    d.ensure('.subdir2', dir=1).join('subfile2').write('secret as well')
    if HASLINK:
        d.join('symlink1').mksymlinkto(str(d.join('subdir1')))
        d.join('symlink2').mksymlinkto('.hidden')
        d.join('symlink3').mksymlinkto('BROKEN')


def test_dir():
    d = Dir({'foo': Dir()})
    assert d.keys() == ['foo']
    py.test.raises(OSError, d.open)
    assert 0 <= d.getsize() <= sys.maxint
    d1 = d.join('foo')
    assert stat.S_ISDIR(d1.kind)
    assert d1.keys() == []
    py.test.raises(OSError, d.join, 'bar')
    st = d.stat()
    assert stat.S_ISDIR(st.st_mode)

def test_file():
    f = File('hello world')
    assert stat.S_ISREG(f.kind)
    py.test.raises(OSError, f.keys)
    assert f.getsize() == 11
    h = f.open()
    data = h.read()
    assert data == 'hello world'
    h.close()
    st = f.stat()
    assert stat.S_ISREG(st.st_mode)
    assert st.st_size == 11

def test_realdir_realfile():
    for show_dotfiles in [False, True]:
        for follow_links in [False, True]:
            v_udir = RealDir(str(udir), show_dotfiles = show_dotfiles,
                                        follow_links  = follow_links)
            v_test_vfs = v_udir.join('test_vfs')
            names = v_test_vfs.keys()
            names.sort()
            assert names == (show_dotfiles * ['.hidden', '.subdir2'] +
                                          ['file1', 'file2', 'subdir1'] +
                             HASLINK * ['symlink1', 'symlink2', 'symlink3'])
            py.test.raises(OSError, v_test_vfs.open)
            assert 0 <= v_test_vfs.getsize() <= sys.maxint

            f = v_test_vfs.join('file1')
            assert f.open().read() == 'somedata1'

            f = v_test_vfs.join('file2')
            assert f.getsize() == len('somelongerdata2')
            py.test.raises(OSError, f.open)

            py.test.raises(OSError, v_test_vfs.join, 'does_not_exist')
            py.test.raises(OSError, v_test_vfs.join, 'symlink3')
            if follow_links:
                d = v_test_vfs.join('symlink1')
                assert stat.S_ISDIR(d.stat().st_mode)
                assert d.keys() == ['subfile1']
                assert d.join('subfile1').open().read() == 'spam'

                f = v_test_vfs.join('symlink2')
                assert stat.S_ISREG(f.stat().st_mode)
                assert f.open().read() == 'secret'
            else:
                py.test.raises(OSError, v_test_vfs.join, 'symlink1')
                py.test.raises(OSError, v_test_vfs.join, 'symlink2')

            if show_dotfiles:
                f = v_test_vfs.join('.hidden')
                assert f.open().read() == 'secret'

                d = v_test_vfs.join('.subdir2')
                assert d.keys() == ['subfile2']
                assert d.join('subfile2').open().read() == 'secret as well'
            else:
                py.test.raises(OSError, v_test_vfs.join, '.hidden')
                py.test.raises(OSError, v_test_vfs.join, '.subdir2')
