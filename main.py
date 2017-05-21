#!/usr/bin/env python3


import math
import os
import subprocess


# NOTE: Ideally, should be localized strings.
#       See: `pydoc locale` and `pydoc gettext`
BYTES_IEC = ('B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB', 'EiB', 'ZiB', 'YiB')
BYTES_SI = ('B', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB')
BITS_IEC = ('b', 'Kib', 'Mib', 'Gib', 'Tib', 'Pib', 'Eib', 'Zib', 'Yib')
BITS_SI = ('b', 'Kb', 'Mb', 'Gb', 'Tb', 'Pb', 'Eb', 'Zb', 'Yb')


class Config(object):

    text = "hello"
    print_size = False
    print_permissions = False
    print_dotfiles = True
    print_git = True
    dir_frmt = {'fg': 'blue', 'frmt': 'bold'}
    dir_listing = True
    sym_frmt = {'fg': 'blue', 'frmt': 'italic'}
    exe_frmt = {'fg': 'green', 'frmt': 'italic'}
    text_frmt = {'fg': 'yellow', 'frmt': 'normal'}
    sym_postfix_frmt = {'fg': 'normal', 'frmt': 'faint'}
    size_frmt = {'fg': 'normal', 'frmt': 'bold'}
    size_postfix_frmt = {'fg': 'normal', 'frmt': 'normal'}
    max_postfix = 30


def human_data_units(size, si_units, iec_units, si=True):
    """Humanize generic data unit sizes (i.e. bytes or bits)."""
    size = float(size)
    if si:
        units = si_units
        multiple = 1e3
    else:
        units = iec_units
        multiple = 2**10
    order = 0  # of magnitude - index for the list above
    while size > multiple:
        size /= multiple
        order += 1
    return size, units[order]


def human_bytes(size, si=True, si_units=BYTES_SI, iec_units=BYTES_IEC):
    """Humanize data sizes to byte units."""
    return human_data_units(size, si_units, iec_units, si)


def pretty_size(size, precision=1, si=True, func=human_bytes):
    """Pretty-print byte-specific data unit sizes."""
    size, unit = func(size, si=si)
    precision = precision if not size.is_integer() else 0
    return '{0:.{prec}f} {1:s}'.format(size, unit, prec=precision)


def normalize_string(string, length):
    for i in range(length - len(string)):
        string = ' ' + string
    return string


class ColorString(object):

    def __init__(self, string, fg="normal", bg="normal", frmt="normal"):
        self.string = string
        self.valid_colors = ["black", "red", "green", "yellow", "blue", "magenta", "cyan", "white", "normal"]
        self.valid_formats = ["normal", "bold", "faint", "italic", "underline", "blinking", "unknown", "inverted"]
        self.colors = {
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
        self.formats = {
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
        self.pre = "\x1b["
        self.post = "\x1b[0m"
        self.set_fg(fg)
        self.set_bg(bg)
        self.set_frmt(frmt)

    def set_fg(self, color):
        if not color in self.valid_colors:
            raise Exception("Not a valid color")
        else:
            self.fg = 30 + self.colors[color]

    def set_bg(self, color):
        if not color in self.valid_colors:
            raise Exception("Not a valid color")
        else:
            self.bg = 40 + self.colors[color]

    def set_frmt(self, frmt):
        if not frmt in self.valid_formats:
            raise Exception("Not a valid format")
        else:
            self.frmt = self.formats[frmt]

    def __repr__(self):
        return self.pre + str(self.frmt) + ";" + str(self.fg) + ";" + str(self.bg) + "m" + self.string + self.post

    def __add__(self, b):
        return self.__repr__() + b


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

    def get_type(self):
        # directory, symlink, file, executable, dotfile, dotfolder
        modetype = oct(self.st_mode)[2:-3]

        if int(modetype) < 10:
            modetype = '00' + modetype
        elif int(modetype) < 100:
            modetype = '0' + modetype

        if modetype == '040':
            self.type = 'directory'
        elif modetype == '100':
            self.type = 'file'
        elif modetype == '120':
            self.type = 'symlink'
        else:
            self.type = 'unknown: ' + modetype

        perm = self.permissions[2]
        if self.type == 'file' and (perm == '1' or perm == '3' or perm == '5' or perm == '6' or perm == '7'):
            self.type = 'executable'

        if self.type != 'symlink' and (self.name == "README" or self.name[-2:] == "md" or self.name[-3:] == "txt"):
            self.type = 'text'

        if self.type == 'symlink':
            self.realpath = os.path.relpath(os.path.realpath(self.name))
            try:
                self.realfile = File(self.realpath)
                if self.realfile.type == 'directory':
                    self.point_to_folder = True
                else:
                    self.point_to_folder = False
            except:
                self.realfile = None

        if (self.name[0] == '.' and not Config.print_dotfiles) or self.name == '.DS_Store' or self.name == '.git' or self.name == '.gitignore':
            self.type = 'noprint'

    def get_permissions(self):
        self.permissions = oct(self.st_mode)[-3:]
        if int(self.permissions) < 10:
            self.type = '00' + self.permissions
        elif int(self.permissions) < 100:
            self.type = '0' + self.permissions

    def get_size(self):
        size_and_postfix = pretty_size(self.st_size)
        size = ''
        lastnum = 0
        for i in range(len(size_and_postfix)):
            if size_and_postfix[i].isdigit() or size_and_postfix[i] == '.':
                size = size + size_and_postfix[i]
                lastnum = i

        postfix = size_and_postfix[lastnum + 2:]
        for i in range(4 - len(size)):
            size = ' ' + size
        for i in range(3 - len(postfix)):
            postfix = postfix + ' '
        self.size = size
        self.size_postfix = postfix

    def set_gitstatus(self, gitstatus):
        self.gitstatus = gitstatus

    def print_gitstatus(self):
        for char in self.gitstatus:
            if char == 'M':
                print(ColorString(char, fg='red', frmt='bold'), end = '')
            elif char == 'A':
                print(ColorString(char, fg='green', frmt='bold'), end = '')
            elif char == 'D':
                print(ColorString(char, fg='red', frmt='bold'), end = '')
            elif char == 'R':
                print(ColorString(char, fg='yellow', frmt='bold'), end = '')
            elif char == 'C':
                print(ColorString(char, fg='cyan', frmt='bold'), end = '')
            elif char == 'U':
                print(ColorString(char, fg='green', frmt='bold'), end = '')
            elif char == '!' or char == '?':
                print(ColorString(char, fg='normal', frmt='faint'), end = '')
            else:
                print(ColorString(char, fg='normal', frmt='bold'), end = '')

    def print_name(self):
        # print(self.type + ": ", end = '')
        if self.type == 'directory':
            print(ColorString(self.name, fg=Config.dir_frmt['fg'], frmt=Config.dir_frmt['frmt']), end = '')
        elif self.type == 'symlink':
            print(ColorString(self.name, fg=Config.sym_frmt['fg'], frmt=Config.sym_frmt['frmt']), end = '')
            if self.realfile != None and self.realfile.type == 'directory':
                print(ColorString('/', fg=Config.sym_frmt['fg'], frmt=Config.sym_frmt['frmt']), end = '')



        elif self.type == 'executable':
            print(ColorString(self.name, fg=Config.exe_frmt['fg'], frmt=Config.exe_frmt['frmt']), end = '')
        elif self.type == 'text':
            print(ColorString(self.name, fg=Config.text_frmt['fg'], frmt=Config.text_frmt['frmt']), end = '')
        else:
            print(self.name, end='')

    def print_size(self):
        print(ColorString(self.size, fg=Config.size_frmt['fg'], frmt=Config.size_frmt['frmt']), end = '')
        print(' ', end = '')
        print(ColorString(self.size_postfix, fg=Config.size_postfix_frmt['fg'], frmt=Config.size_postfix_frmt['frmt']), end = '')

    def print_postfix(self, spaceleft, listing = True):
        if self.type == 'directory':
            print(ColorString('/', fg=Config.dir_frmt['fg'], frmt=Config.dir_frmt['frmt']), end = '')
            contents = [str(filename) for filename in os.listdir(self.name)]
            contents.sort()

            is_empty = True
            for filename in contents:
                if not filename[0] == '.':
                    is_empty = False
                    break

            if Config.dir_listing and not is_empty:
                print(' ', end = '')

                files_string = ''
                numfiles = 0
                for filename in contents:
                    if not filename[0] == '.':
                        files_string = files_string + ', ' + filename
                        numfiles += 1
                if numfiles > 0:
                    numlen = math.log(numfiles, 10) + 1
                else:
                    numlen = 1

                cumulative_length = 15 + numlen
                if numfiles == 1: cumulative_length -= 1

                if '.git' in contents:
                    print(ColorString('(git repo) ', fg='magenta', frmt='faint'), end = '')
                    cumulative_length += 11
                print(ColorString('(', frmt='faint'), end = '')


                files_string = files_string[2:]

                added = False
                for ch in files_string:
                    if cumulative_length > spaceleft:
                        print(ColorString('...', frmt='faint'), end = '')
                        added = True
                        break
                    print(ColorString(ch, frmt='faint'), end = '')
                    cumulative_length += 1
                if not added:
                    cumulative_length -= 3

                print(ColorString(')', frmt='faint'), end = '')
                while cumulative_length < spaceleft:
                    print(' ', end = '')
                    cumulative_length += 1
                if numfiles != 1:
                    print(ColorString(' [' + str(numfiles) + ' files]', frmt='faint'))
                else:
                    print(ColorString(' [' + str(numfiles) + ' file]', frmt='faint'))

            else:
                cum_len = 7
                while cum_len < spaceleft:
                    print(' ', end = '')
                    cum_len += 1
                print(ColorString("[empty]", frmt='faint'))
        elif self.type == 'symlink':
            print(ColorString(" -> ", frmt='bold'), end = '')
            print(ColorString(self.realpath, fg=Config.sym_postfix_frmt['fg'], frmt=Config.sym_postfix_frmt['frmt']), end = '')
            if self.realfile != None and self.realfile.type == 'directory':
                print(ColorString('/', fg=Config.sym_postfix_frmt['fg'], frmt=Config.sym_postfix_frmt['frmt']), end = '')
            print()
        else:
            if self.st_size == 0:
                cum_len = 6
                while cum_len < spaceleft:
                    print(' ', end = '')
                    cum_len += 1
                print(ColorString("[empty]", frmt='faint'))
            else:
                try:
                    with open(self.name) as f:
                        lines = 0
                        for line in f:
                            lines += 1
                        if lines > 0:
                            lines_lenght = int(math.log(lines, 10)) + 1
                        else:
                            lines_lenght = 1
                        if lines == 1:
                            lines_lenght -= 1
                        cumulative_length = 15 + lines_lenght
                    with open(self.name) as f:
                        lines_string = ''
                        for line in f:
                            lines_string = lines_string + ' ' + line.strip('\n')
                        lines_string = lines_string[1:]

                    print(ColorString(" (", frmt='faint'), end ='')
                    added = False
                    for ch in lines_string:
                        if cumulative_length > spaceleft:
                            print(ColorString('...', frmt='faint'), end = '')
                            added = True
                            break
                        print(ColorString(ch, frmt='faint'), end = '')
                        cumulative_length += 1
                    if not added: cumulative_length -= 4

                    print(ColorString(')', frmt='faint'), end = '')
                    while cumulative_length < spaceleft:
                        print(' ', end = '')
                        cumulative_length += 1
                    if lines != 1:
                        print(ColorString(' [' + str(lines) + ' lines]', frmt='faint'))
                    else:
                        print(ColorString(' [' + str(lines) + ' line]', frmt='faint'))
                except:
                    print()
                    pass

    def print_permissions(self):
        print(self.permissions, end = '')


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
            cmd = ['git', 'status', '--short', '--ignored', '--porcelain'],
            result = subprocess.check_output(cmd, universal_newlines=True).splitlines()
        except:
            print('git status doesn\'t work')
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
        if self.has_gitrepo and self.has_gitrepo:
            try:
                cmd = ['git', 'rev-parse', '--abbrev-ref', 'HEAD']
                result = subprocess.check_output(cmd, universal_newlines=True).splitlines()
                print(ColorString(result, fg='cyan', frmt='bold'), end = '')
                print(ColorString(":", frmt='bold'))
            except:
                pass
        try:
            rows, columns = os.popen('stty size', 'r').read().split()
        except:
            columns = 80
        for filename in self.files:
            spaceleft = int(columns)
            if not filename.type == 'noprint':
                if Config.print_permissions:
                    filename.print_permissions()
                    print(' ', end = '')
                if Config.print_size:
                    filename.print_size()
                    print(' ', end = '')
                if Config.print_git and self.has_gitrepo:
                    filename.print_gitstatus()
                    print(' ', end = '')
                    spaceleft -= 3
                filename.print_name()
                spaceleft -= len(filename.name) + 1
                filename.print_postfix(spaceleft)


if __name__ == "__main__":
    Files('.').print_files()
