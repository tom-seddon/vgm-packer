#!/usr/bin/env python
# 
##########################################################################
##########################################################################
# 
# "MIT License":
#
# Permission is hereby granted, free of charge, to any person
# obtaining a copy of this software and associated documentation files
# (the "Software"), to deal in the Software without restriction,
# including without limitation the rights to use, copy, modify, merge,
# publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS
# BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
# ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
##########################################################################
##########################################################################
#
# Pack a .vgc file into multiple ROM banks, probably for a Master 128
# demo where you'd like to keep main RAM free.
#
# Specify output stem STEM with -o. The tool writes out STEM.4.dat,
# STEM.5.dat, and so on, one per ROM bank, named after the ROM bank
# it's to be loaded into. It also writes out STEM.toc.dat, which needs
# including into your code (not in a ROM bank! - don't worry, it's
# quite small) and passing into vgm_mount.
#
# Then just play as normal.
#
# By default, the tool assumes ROM banks 4, 5, 6 and 7 are available,
# as per the Master. Supply the actual list of banks available using
# --bank. For example, --bank 45 if trying to stick to a budget.
# 
# The bank numbers are written into the TOC, and will be used to set
# ROMSEL.
#
# Autodetecting sideway RAM banks at runtime isn't really supported -
# you're assumed to be writing for the Master, so you know which slots
# are available ahead of time. It ought to be possible to specify
# something like --bank 01234 (or whatever), then fix up the TOC table
# at runtime.
#
##########################################################################
##########################################################################

import sys,argparse,collections,itertools

##########################################################################
##########################################################################

g_verbose=False

def V(x):
    if g_verbose:
        sys.stdout.write(x)
        sys.stdout.flush()

def fatal(x):
    sys.stderr.write('FATAL: ')
    sys.stderr.write(x)
    sys.stderr.write('\n')
    sys.exit(1)

##########################################################################
##########################################################################

def load_file(path):
    with open(path,'rb') as f: return [ord(x) for x in f.read()]
    
##########################################################################
##########################################################################

def save_file(path,xs):
    with open(path,'wb') as f: f.write(''.join([chr(x) for x in xs]))

##########################################################################
##########################################################################

def ensure_ok(data):
    # the actual minimum size is larger than this, of course...
    if len(data)<4: fatal('input file too small')

    if data[0]!=0x56 or data[1]!=0x47 or data[2]!=0x43:
        fatal('file doesn\'t have VGC header')

    if data[3]&0x80: fatal('Huffman compression not supported')

##########################################################################
##########################################################################

VgcStream=collections.namedtuple('VgcStream','index data')

# see vgm_stream_mount.
def find_vgc_streams(data):
    starts=[]
    index=7

    for i in range(8):
        starts.append(index)

        n=data[index+0]<<0|data[index+1]<<8
        n+=4

        index+=n

    starts.append(index)

    streams=[VgcStream(i,data[starts[i]:starts[i+1]]) for i in range(8)]
    return streams

##########################################################################
##########################################################################

def find_order(streams,
               options):
    # It doesn't take long to just try every permutation...
    best_order=None
    best_num_roms=16

    for order in itertools.permutations(streams):
        rom_size=0
        num_roms=1
        for stream in order:
            if rom_size+len(stream.data)>16384:
                num_roms+=1
                rom_size=0

            rom_size+=len(stream.data)

        if num_roms<best_num_roms:
            best_num_roms=num_roms
            best_order=order[:]

    # produce list of streams that go in each ROM.
    roms=[]
    rom_size=16385
    for stream in best_order:
        if rom_size+len(stream.data)>16384:
            rom=[]
            roms.append(rom)
            rom_size=0

        rom.append(stream)
        rom_size+=len(stream.data)

    return roms

##########################################################################
##########################################################################

StreamLocation=collections.namedtuple('StreamLocation','bank addr')

def save_files(roms,options):
    stream_locations=8*[None]
    
    for i,streams in enumerate(roms):
        rom=[]
        addr=0x8000
        for stream in streams:
            stream_locations[stream.index]=StreamLocation(options.banks[i],
                                                          addr)
            rom+=stream.data
            addr+=len(stream.data)
        save_file('%s.%x.dat'%(options.output_stem,
                               options.banks[i]),
                  rom)

    toc=[ord('V'),ord('G'),ord('C'),
         0x20,
         0,0,0]                 # ???

    for stream_location in stream_locations:
        toc.append(stream_location.bank)
        toc.append(stream_location.addr>>0&0xff)
        toc.append(stream_location.addr>>8&0xff)

    save_file('%s.toc.dat'%options.output_stem,toc)

##########################################################################
##########################################################################

def isxdigit(c): return c in "0123456789ABCDEFabcdef"

def handle_options(options):
    banks=[]
    for bank in options.banks:
        if not isxdigit(bank): fatal('bank not hex digit: "%s"'%bank)
        if bank in banks: fatal('bank duplicated: "%s"'%bank)
        banks.append(int(bank,16))

    options.banks=banks
            
##########################################################################
##########################################################################

def main(options):
    global g_verbose
    g_verbose=options.verbose

    handle_options(options)

    input_data=load_file(options.input_path)

    ensure_ok(input_data)

    streams=find_vgc_streams(input_data)

    V('Stream sizes:\n')
    for stream in streams:
        V('%d. %d bytes\n'%(stream.index,len(stream.data)))

    for stream in streams:
        if len(stream.data)>16384:
            fatal('stream %d is %d bytes - data can never fit in ROM'%(stream.index,len(stream.data)))
            
    roms=find_order(streams,options)

    V('Data fits in %d ROMs:\n'%len(roms))
    for i,streams in enumerate(roms):
        if i<len(options.banks): bank='%x'%options.banks[i]
        else: bank='?'
        V('ROM %d (bank %s):\n'%(i,bank))
        addr=0x8000
        for stream in streams:
            V('    $%04x. Stream %d\n'%(addr,stream.index))
            addr+=len(stream.data)

        num_bytes_free=0xc000-addr
        V('    (%d ($%04x) byte(s) free)\n'%(num_bytes_free,num_bytes_free))

    if len(roms)>len(options.banks):
        fatal('data requires %d ROM(s) - %d banks available'%(len(roms),len(options.banks)))

    save_files(roms,options)

##########################################################################
##########################################################################

# http://stackoverflow.com/questions/25513043/python-argparse-fails-to-parse-hex-formatting-to-int-type
def auto_int(x): return int(x,0)

def vgcsplit(argv):
    parser=argparse.ArgumentParser('fit .vgc file into ROM banks')

    parser.add_argument('-v',
                        '--verbose',
                        action='store_true',
                        help='be more verbose')
    
    parser.add_argument('-o',
                        '--output',
                        dest='output_stem',
                        metavar='STEM',
                        help='write data into ROM files named %(metavar)s.BANK.dat, and header named %(metavar)s.toc.dat')
    
    parser.add_argument('--banks',
                        default='4567',
                        metavar='BANKS',
                        help='specify banks available for use, a list of hex digits. Default: %(default)s')
    
    parser.add_argument('input_path',
                        metavar='VGC-FILE',
                        help='read VGC data from %(metavar)s')

    main(parser.parse_args(argv))

##########################################################################
##########################################################################
    
if __name__=='__main__': vgcsplit(sys.argv[1:])

# Local Variables:
# indent-tabs-mode: t
# End:
