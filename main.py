#!/usr/bin/env python3

from __future__ import print_function

import fcntl
import math
import os
import shlex
import struct
import subprocess
import termios


# NOTE: Ideally, should be localized strings.
#       See: `pydoc locale` and `pydoc gettext`
BYTES_IEC = ('B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB', 'EiB', 'ZiB', 'YiB')
BYTES_SI = ('B', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB')


class Config(object):

    print_ownerpermissions = False
    print_grouppermissions = False
    print_ottherpermissions = False
    print_size = False
    print_git = True
    print_aftertext = True

    dir_frmt = {'fg': 'blue', 'frmt': 'bold'}
    sym_frmt = {'fg': 'blue', 'frmt': 'italic'}
    dot_frmt = {'fg': 'normal', 'frmt': 'italic'}
    program_frmt = {'fg': 'normal', 'frmt': 'bold'}
    makefile_frmt = {'fg': 'magenta', 'frmt': 'normal'}
    exe_frmt = {'fg': 'green', 'frmt': 'italic'}
    text_frmt = {'fg': 'yellow', 'frmt': 'normal'}

    size_frmt = {'fg': 'normal', 'frmt': 'bold'}
    size_postfix_frmt = {'fg': 'normal', 'frmt': 'normal'}

    print_dotfiles = True

    noprint_files = ['.DS_Store', '__pycache__/']




def normalize_string(string, length):
    for i in range(length - len(string)):
        string = ' ' + string
    return string

def colorize_string(string, fg="normal", bg="normal", frmt="normal"):
    valid_colors = ["black", "red", "green", "yellow", "blue", "magenta", "cyan", "white", "normal"]
    valid_formats = ["normal", "bold", "faint", "italic", "underline", "blinking", "unknown", "inverted"]
    colors = {
        "black" : 0,
        "red" : 1,
        "green" : 2,
        "yellow" : 3,
        "blue" : 4,
        "magenta" : 5,
        "cyan" : 6,
        "white" : 7,
        "normal" : 8,
    }
    formats = {
        "normal" : 0,
        "bold" : 1,
        "faint" : 2,
        "italic" : 3,
        "underline" : 4,
        "slowblink" : 5,
        "rapidblink" : 6,   # NS
        "negative" : 7,
        "conceal" : 8,      # NS
        "crossedout" : 9,   # NA
    }
    pre = "\x1b["
    post = "\x1b[0m"
        
    if not fg in valid_colors:
        raise Exception("Not a valid color")
    if not bg in valid_colors:
        raise Exception("Not a valid color")
    if not frmt in valid_formats:
        raise Exception("Not a valid format")

    fg = 30 + colors[fg]
    bg = 40 + colors[bg]
    frmt = formats[frmt]
    return pre + str(frmt) + ";" + str(fg) + ";" + str(bg) + "m" + string + post

class File(object):

    def __init__(self, name):
        self.name = name
        self.index_stat()

        self.get_permissions()
        self.get_type()
        self.get_size()

    def index_stat(self):
        st = os.lstat(self.name)
        self.st_mode = st[0]
        self.st_size = st[6]

    def get_permissions(self):

        def index_permissions(number):
            if number == 0: return {'read': False, 'write': False, 'exec': False}
            elif number == 1:
                return {'read': False, 'write': False, 'exec': True}
            elif number == 2:
                return {'read': True, 'write': False, 'exec': False}
            elif number == 3:
                return {'read': False, 'write': True, 'exec': True}
            elif number == 4:
                return {'read': True, 'write': False, 'exec': False}
            elif number == 5:
                return {'read': True, 'write': False, 'exec': True}
            elif number == 6:
                return {'read': True, 'write': True, 'exec': False}
            elif number == 7:
                return {'read': True, 'write': True, 'exec': True}
            else:
                return {'read': False, 'write': False, 'exec': False}
            
            
        permnum = oct(self.st_mode)[-3:]

        self.permissions = {}
        self.permissions['owner'] = index_permissions(int(permnum[0]))
        self.permissions['group'] = index_permissions(int(permnum[1]))
        self.permissions['others'] = index_permissions(int(permnum[2]))

    def get_type(self):
        ''' supported types are: (directory, exectuable, symlink, text, file, dotfile)
        todo: pictures'''

        modetype = oct(self.st_mode)[2:-3]
        self.modetype = modetype

        if modetype in ['040', '40']:
            self.type = 'directory'
            self.name += '/'

        elif modetype == '100' and self.permissions['owner']['exec']:
            self.type = 'executable'

        elif modetype == '120':
            self.type = 'symlink'
            self.realpath = os.path.relpath(os.path.realpath(self.name))
            try:
                self.realfile = File(self.realpath)
                if self.realfile.type == 'directory':
                    self.name += '/'
            except:
                self.realfile = None
        else:
            if self.name in ['README', 'readme'] or self.name[-2:] == "md" or self.name[-3:] == "txt":
                self.type = 'text'
            elif self.name[-2:] in ['.c'] or self.name[-3:] in ['.py']:
                self.type = 'program'
            elif self.name in ['Makefile', 'makefile']:
                self.type = 'makefile'
            else:
                self.type = 'file'

        if self.name[0] == '.' and self.name[1] != '.':
            self.type = 'dotfile'
            

    def get_size(self):

        def human_size(size, precision=0):
            size = float(size)
            units = ('B', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB')
            multiple = 1e3
            order = 0  # of magnitude - index for the list above
            while size > multiple:
                size /= multiple
                order += 1

            unit = units[order]

            precision = precision if not size.is_integer() else 0
            return '{0:.{prec}f} {1:s}'.format(size, unit, prec=precision)

        size_and_postfix = human_size(self.st_size)
        size = ''
        lastnum = 0
        for i in range(len(size_and_postfix)):
            if size_and_postfix[i].isdigit() or size_and_postfix[i] == '.':
                size = size + size_and_postfix[i]
                lastnum = i

        self.size_postfix = size_and_postfix[lastnum + 2:]
        self.size = size




    def set_gitstatus(self, gitstatus):
        self.gitstatus = gitstatus

    def print_gitstatus(self):
        for char in self.gitstatus:
            if char == 'M':
                print(colorize_string(char, fg='red', frmt='bold'), end='')
            elif char == 'A':
                print(colorize_string(char, fg='green', frmt='bold'), end='')
            elif char == 'D':
                print(colorize_string(char, fg='red', frmt='bold'), end='')
            elif char == 'R':
                print(colorize_string(char, fg='yellow', frmt='bold'), end='')
            elif char == 'C':
                print(colorize_string(char, fg='cyan', frmt='bold'), end='')
            elif char == 'U':
                print(colorize_string(char, fg='green', frmt='bold'), end='')
            elif char == '!' or char == '?':
                print(colorize_string(char, fg='normal', frmt='faint'), end='')
            else:
                print(colorize_string(char, fg='normal', frmt='bold'), end='')

    def print_name(self):

        if self.type == 'directory':
            print(colorize_string(self.name, fg=Config.dir_frmt['fg'], frmt=Config.dir_frmt['frmt']), end = '')
        elif self.type == 'executable':
            print(colorize_string(self.name, fg=Config.exe_frmt['fg'], frmt=Config.exe_frmt['frmt']), end='')
        elif self.type == 'symlink':
            print(colorize_string(self.name, fg=Config.sym_frmt['fg'], frmt=Config.sym_frmt['frmt']), end='')
        elif self.type == 'text':
            print(colorize_string(self.name, fg=Config.text_frmt['fg'], frmt=Config.text_frmt['frmt']), end='')
        elif self.type == 'dotfile':
            print(colorize_string(self.name, fg=Config.dot_frmt['fg'], frmt=Config.dot_frmt['frmt']), end='')
        elif self.type == 'program':
            print(colorize_string(self.name, fg=Config.program_frmt['fg'], frmt=Config.program_frmt['frmt']), end='')
        elif self.type == 'makefile':
            print(colorize_string(self.name, fg=Config.makefile_frmt['fg'], frmt=Config.makefile_frmt['frmt']), end='')
        else:
            print(self.name, end='')

    def print_size(self):
        size = self.size
        postfix = self.size_postfix

        for i in range(3 - len(size)):
            size = ' ' + size
        if len(postfix) == 1:
            postfix += ' '

        print(colorize_string(size, fg=Config.size_frmt['fg'], frmt=Config.size_frmt['frmt']), end='')
        print(colorize_string(postfix, fg=Config.size_postfix_frmt['fg'], frmt=Config.size_postfix_frmt['frmt']), end='')

    def print_aftertext(self, spaceleft, listing = True):
        
        print(end = ' ')
        spaceleft -= 1

        def print_finite(prefix, postfix, var_string, spaceleft):
            
            prelen = len(prefix)
            postlen = len(postfix)
            strlen = len(var_string)

            if not var_string and (prelen + postlen + 1 <= spaceleft): # No var_string
                print(colorize_string(prefix, frmt='faint'), end = '')
                for i in range(spaceleft - (prelen + postlen)):
                    print(' ', end = '')
                print(colorize_string(postfix, frmt='faint'), end = '')
                return

            if prelen + strlen + postlen + 4 <= spaceleft: # Everything goes nicely
                print(colorize_string(prefix + ' (' + var_string + ') ', frmt='faint'), end = '')
                for i in range(spaceleft - (prelen + strlen + postlen + 4)):
                    print(' ', end = '')
                print(colorize_string(postfix, frmt='faint'), end = '')
                return

            if prelen + postlen + 6 >= spaceleft: # No space for var_string segment + pre/post
                if prelen + postlen + 1 <= spaceleft:
                    print(colorize_string(prefix, frmt='faint'), end = '')
                    for i in range(spaceleft - (prelen + postlen)):
                        print(' ', end = '')
                    print(colorize_string(postfix, frmt='faint'), end = '')

                elif prelen <= spaceleft:
                    print(colorize_string(prefix, frmt='faint'), end = '')
                elif postlen <= spaceleft:
                    for i in range(spaceleft - prelen):
                        print(end = ' ')
                    print(colorize_string(postfix, frmt='faint'), end = '')
                return

            var_string = var_string[: (spaceleft - (prelen + postlen + 6))]
            print(colorize_string(prefix + ' (' + var_string + '..) ' + postfix, frmt='faint'), end = '')
            
        if self.type == 'directory':
            contents = [str(filename) for filename in os.listdir(self.name)]
            contents.sort()
            numfiles = 0
            files_string = ''
            for filename in contents:
                if not filename[0] == '.':
                    files_string = files_string + ', ' + filename
                    numfiles += 1
            files_string = files_string[2:]

            if '.git' in contents:
                    print(colorize_string('(git repo) ', fg='magenta', frmt='faint'), end='')
                    spaceleft -= 11

            if numfiles == 1:
                postfix = '[' + str(numfiles) + ' file]'
            else:
                postfix = '[' + str(numfiles) + ' files]'
                
            var_string = files_string
            prefix = '[' + self.size + self.size_postfix + ']'
            print_finite(prefix, postfix, var_string, spaceleft)

        elif self.type == 'symlink':
            print(colorize_string("-> ", frmt='bold'), end = '')
            spaceleft -= 3
            if not self.realfile == None:
                self.realfile.print_name()
                spaceleft -= len(self.realfile.name)
                self.realfile.print_aftertext(spaceleft)
            else:
                print(colorize_string(self.realpath, fg='normal', frmt='italic'), end = '')

        else:
            if self.type == 'program':
                if self.name[-2:] == '.c':
                    try:
                        cmd = shlex.split('grep "int main(" ' + self.name)
                        result = subprocess.check_output(cmd, universal_newlines=True).rstrip()
                        if 'int main(' in result:
                            print(colorize_string('(main) ', fg='magenta', frmt='faint'), end='')
                            spaceleft -= 7
                    except:
                        pass
            if self.st_size == 0:
                print_finite('(empty)', '', '', spaceleft)
            else:
                try:
                    with open(self.name) as f:
                        lines_string = ''
                        lines = 0
                        for line in f:
                            lines += 1
                            lines_string = lines_string + ' ' + line.strip('\n').strip('\t')
                        lines_string = lines_string[1:]
                        if lines == 1:
                            postfix = '[' + str(lines) + ' line]'
                        else:
                            postfix = '[' + str(lines) + ' lines]'
                        prefix = '[' + self.size + self.size_postfix + ']'
                        var_string = lines_string
                        print_finite(prefix, postfix, var_string, spaceleft)
                except:
                    pass

    def __print_permissions(self, permissions):
        if permissions['read']:
            print(colorize_string('r', fg='yellow', frmt='bold'), end='')
        else:
            print('-', end = '')
        if permissions['write']:
            print(colorize_string('w', fg='red', frmt='bold'), end='')
        else:
            print('-', end = '')
        if permissions['exec']:
            print(colorize_string('x', fg='green', frmt='bold'), end='')
        else:
            print('-', end = '')

    def print_ownerpermissions(self):
        self.__print_permissions(self.permissions['owner'])

    def print_grouppermissions(self):
        self.__print_permissions(self.permissions['group'])

    def print_otherspermissions(self):
        self.__print_permissions(self.permissions['others'])


class Files(object):

    def __init__(self, folder):
        self.folder = os.path.realpath(folder)
        self.files = [ ]
        self.has_gitrepo = False

        for name in os.listdir("."):
            if name == '.git':
                self.has_gitrepo = True
            curfile = File(name)
            self.files.append(curfile)

        if self.has_gitrepo:
            self.initialize_git()

    def initialize_git(self):
        try:
            cmd = shlex.split('git status --short --ignored --porcelain')
            result = subprocess.check_output(cmd, universal_newlines=True).splitlines()
        except:
            self.has_gitrepo = False
            return

        git_status = {}
        for line in result:
            git_status[line.strip('/')[3:]] = line.strip('/')[:2]

        for filename in self.files:
            if filename.name in git_status:
                filename.set_gitstatus(git_status[filename.name])
            else:
                filename.set_gitstatus('  ')

    def print_files(self):
        if self.has_gitrepo and Config.print_git:
            try:
                cmd = shlex.split('git rev-parse --abbrev-ref HEAD')
                result = subprocess.check_output(cmd, universal_newlines=True).rstrip()
                print(colorize_string(' branch: ', fg='cyan', frmt='bold'), end = '')
                print(colorize_string(result, frmt='normal'))

                cmd = shlex.split('git log -1')
                result = subprocess.check_output(cmd, universal_newlines=True)
                buf = ''
                name = 'unknown'
                i = 0
                for ch in result:
                    buf = buf + ch
                    if ch == '\n':
                        i += 1
                        if i == 5:
                            while buf[0] == ' ':
                                buf = buf[1:]
                            print(colorize_string(' lastest commit ', fg='yellow', frmt='normal'), end='')
                            print(colorize_string(": ", frmt='bold'), end = '')
                            print(colorize_string('"' + buf.rstrip() + '"', fg='normal', frmt='italic'), end = '')
                            print(colorize_string(' (by ' + name + ')'))
                            break
                        if i == 2:
                            name = buf
                            name = name[8:]
                            r = 0
                            for ch in name:
                                if ch == '<':
                                    name = name[:r - 1]
                                r += 1
                        buf = ''
            except:
                pass
        try:
            h, w, hp, wp = struct.unpack('HHHH', fcntl.ioctl(0, termios.TIOCGWINSZ, struct.pack('HHHH', 0, 0, 0, 0)))
            columns = w
        except:
            columns = 80

        for filename in self.files:
            spaceleft = int(columns)

            if filename.name in Config.noprint_files:
                continue

            if Config.print_ownerpermissions:
                filename.print_ownerpermissions()
                spaceleft -= 3
            if Config.print_grouppermissions:
                filename.print_grouppermissions()
                spaceleft -= 3
            if Config.print_ottherpermissions:
                filename.print_otherspermissions()
                spaceleft -= 3
            if Config.print_ottherpermissions or Config.print_grouppermissions or Config.print_ownerpermissions:
                print(' ', end = '')
                spaceleft -= 1

            if Config.print_size:
                filename.print_size()
                print(' ', end='')
                spaceleft -= 6

            if Config.print_git and self.has_gitrepo:
                filename.print_gitstatus()
                print(' ', end='')
                spaceleft -= 3

            filename.print_name()
            spaceleft -= len(filename.name)

            if Config.print_aftertext:
                filename.print_aftertext(spaceleft)
            print()

if __name__ == "__main__":
    Files('.').print_files()
