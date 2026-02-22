#!/usr/bin/env python
import sys

infile, outfile = sys.argv[1:3]

with open(infile, 'rb') as f_in:
    with open(outfile, 'wb') as f_out:
        while True:
            sector = f_in.read(2352)
            if len(sector) < 2352:
                break
            f_out.write(sector[16:2064])

print("Converted %s -> %s" % (infile, outfile))

