# Copyright (C) 2026 CEA
#
# This file is part of Rift project.
#
# This software is governed by the CeCILL license under French law and
# abiding by the rules of distribution of free software.  You can  use,
# modify and/ or redistribute the software under the terms of the CeCILL
# license as circulated by CEA, CNRS and INRIA at the following URL
# "http://www.cecill.info".
#
# As a counterpart to the access to the source code and  rights to copy,
# modify and redistribute granted by the license, users are provided only
# with a limited warranty  and the software's author,  the holder of the
# economic rights,  and the successive licensors  have only  limited
# liability.
#
# In this respect, the user's attention is drawn to the risks associated
# with loading,  using,  modifying and/or developing or reproducing the
# software by the user in light of its specific status of free software,
# that may mean  that it is complicated to manipulate,  and  that  also
# therefore means  that it is reserved for developers  and  experienced
# professionals having in-depth computer knowledge. Users are therefore
# encouraged to load and test the software's suitability as regards their
# requirements in conditions enabling the security of their systems and/or
# data to be ensured and,  more generally, to use and operate it in the
# same conditions as regards security.
#
# The fact that you are presently reading this means that you have had
# knowledge of the CeCILL license and that you accept its terms.
#

"""
Utils class for the annexes
"""
import hashlib
import string

# List of ASCII printable characters
_TEXTCHARS = bytearray([9, 10, 13] + list(range(32, 127)))

# Suffix of metadata filename
_INFOSUFFIX = '.info'

def get_digest_from_path(path):
    """Get file id from the givent path"""
    return open(path, encoding='utf-8').read()

def get_info_from_digest(digest):
    """Get file info id"""
    return digest + _INFOSUFFIX

def is_binary(filepath, blocksize=65536):
    """
    Look for non printable characters in the first blocksize bytes of filepath.

    Note it only looks for the first bytes. If binary data appeared farther in
    that file, it will be wrongly detected as a non-binary one.

    If there is a very small number of binary characters compared to the whole
    file, we still consider it as non-binary to avoid using Annex uselessly.
    """
    with open(filepath, 'rb') as srcfile:
        data = srcfile.read(blocksize)
        binchars = data.translate(None, _TEXTCHARS)
        if len(data) == 0:
            result = False
        # If there is very few binary characters among the file, consider it as
        # plain us-ascii.
        elif float(len(binchars)) / float(len(data)) < 0.01:
            result = False
        else:
            result = bool(binchars)
    return result

def is_pointer(filepath):
    """
    Return true if content of file at filepath looks like a valid digest
    identifier.
    """
    try:
        with open(filepath, encoding='utf-8') as fh:
            identifier = fh.read()
            # Remove possible trailing whitespace, newline and carriage return
            # characters.
            identifier = identifier.rstrip()

    except UnicodeDecodeError:
        # Binary fileis cannot be decoded with UTF-8
        return False

    # Check size corresponds to MD5 (32) or SHA3 256 (64).
    if len(identifier) in (32, 64):
        return all(byte in string.hexdigits for byte in identifier)

    # If the identifier is not a valid Rift Annex pointer
    return False

def hashfile(filepath, iosize=65536):
    """Compute a digest of filepath content."""
    hasher = hashlib.sha3_256()
    with open(filepath, 'rb') as srcfile:
        buf = srcfile.read(iosize)
        while len(buf) > 0:
            hasher.update(buf)
            buf = srcfile.read(iosize)
    return hasher.hexdigest()
