#  -*- coding: utf8 -*-

"""MARC record processing tools used within samiTools."""

# Import required modules

from samiTools.sami_functions import *

__author__ = 'Victoria Morris'
__license__ = 'MIT License'
__version__ = '1.0.0'
__status__ = '4 - Beta Development'


# ====================
#     Constants
# ====================

LEADER_LENGTH, DIRECTORY_ENTRY_LENGTH = 24, 12
SUBFIELD_INDICATOR, END_OF_FIELD, END_OF_RECORD = chr(0x1F), chr(0x1E), chr(0x1D)
ALEPH_CONTROL_FIELDS = ['DB ', 'SYS', 'LDR']

SUBS = OrderedDict([
    ('c', re.compile(r'<copyNumber>(.*?)</copyNumber>')),
    ('i', re.compile(r'<itemID>(.*?)</itemID>')),
    ('d', re.compile(r'<dateCreated>(.*?)</dateCreated>')),
    ('k', re.compile(r'<location>(.*?)</location>')),
    ('l', re.compile(r'<homeLocation>(.*?)</homeLocation>')),
    ('m', None),
    ('t', re.compile(r'<type>(.*?)</type>')),
    ('u', re.compile(r'<dateModified>(.*?)</dateModified>')),
    ('x', re.compile(r'<category1>(.*?)</category1>')),
    ('z', re.compile(r'<category2>(.*?)</category2>')),
])


XML_HEADER = '<?xml version="1.0" encoding="UTF-8" ?>' \
             '\n<marc:collection xmlns:marc="http://www.loc.gov/MARC21/slim" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" ' \
             'xsi:schemaLocation="http://www.loc.gov/MARC21/slim http://www.loc.gov/standards/marcxml/schema/MARC21slim.xsd">'

# ====================
#     Exceptions
# ====================


class RecordLengthError(Exception):
    def __str__(self): return 'Invalid record length in first 5 bytes of record'


class LeaderError(Exception):
    def __str__(self): return 'Error reading record leader'


class DirectoryError(Exception):
    def __str__(self): return 'Record directory is invalid'


class FieldsError(Exception):
    def __str__(self): return 'Error locating fields in record'


class BaseAddressLengthError(Exception):
    def __str__(self): return 'Base address exceeds size of record'


class BaseAddressError(Exception):
    def __str__(self): return 'Error locating base address of record'


class RecordWritingError(Exception):
    def __str__(self): return 'Error writing record'


# ====================
#       Classes
# ====================


class SAMIReader(object):
    def __init__(self, target, reader_type):
        if hasattr(target, 'read') and callable(target.read):
            self.file_handle = target
        self.reader_type = reader_type

    def __iter__(self):
        return self

    def close(self):
        if self.file_handle:
            self.file_handle.close()
            self.file_handle = None

    def __next__(self):
        chunk = ''
        line = self.file_handle.readline()
        if not line: raise StopIteration
        while chunk == '' and line and self.new_record(line):
            line = self.file_handle.readline()
            if not line: break
        while line and not self.new_record(line):
            chunk += line
            line = self.file_handle.readline()
            if not line: break
        if not chunk: raise StopIteration
        return SAMIRecord(chunk, record_type=self.reader_type)

    def new_record(self, line):
        if self.reader_type == 'prn':
            if any(s in line for s in ['<?xml version', '<title>', '<report>', '</report>', '<dateFormat>', '<catalog>']): return True
            if re.search(r'^<dateCreated>[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}</dateCreated>$', line.strip()): return True
            return False
        if self.reader_type == 'xml':
            if any(s in line for s in ['<record xmlns="http://www.loc.gov/mods/v3">', '<?xml version', '<OAI-PMH',
                                       '<ListRecords>', '</ListRecords>']): return True
            return False
        if self.reader_type == 'txt':
            if '*** DOCUMENT BOUNDARY ***' in line: return True
            return False
        return False


class SAMIRecord(object):

    def __init__(self, data, record_type):
        self.record_type = record_type
        self.record = MARCRecord()
        self.data = data

        if self.record_type == 'prn':
            for field in re.findall(r'<marcEntry tag="(.*?)" label="(.*?)" ind="(.*?)">(.*?)</marcEntry>', self.data):
                tag, label, ind1, ind2, content = field[0], field[1], field[2][0], field[2][1], field[3]
                try: test = int(tag)
                except: test = None
                if tag == '000' or (test and test < 10) or tag in ALEPH_CONTROL_FIELDS:
                    try: f = Field(tag=tag, data=content.split('|a', 1)[1].strip())
                    except: f = Field(tag=tag, data=content.strip())
                else:
                    subfields = []
                    for s in content.split('|')[1:]:
                        try: subfields.extend([s[0], s[1:]])
                        except: pass
                    f = Field(tag=tag, indicators=[ind1, ind2], subfields=subfields)
                self.record.add_ordered_field(f)
            self.data = ''.join(line for line in self.data.split('\n'))
            for call in re.findall(r'<call>(.*?)</call>', self.data):
                try: call_number = re.search(r'<callNumber>(.*?)</callNumber>', call).group(1)
                except: call_number = '[NO CALL NUMBER]'
                try: library = re.search(r'<library>(.*?)</library>', call).group(1)
                except: library = None
                for item in re.findall(r'<item>(.*?)</item>', call):
                    subfields = ['a', call_number, 'w', 'ALPHANUM']
                    for s in SUBS:
                        if s == 'm':
                            if library:
                                subfields.extend(['m', library])
                            subfields.extend(['r', 'Y', 's', 'Y'])
                        else:
                            try: subfields.extend([s, re.search(SUBS[s], item).group(1).strip()])
                            except:
                                if s == 'u':
                                    try: subfields.extend([s, re.search(SUBS['d'], item).group(1).strip()])
                                    except: pass
                                else: pass
                    f = Field(tag='999', indicators=[' ', ' '], subfields=subfields)
                    self.record.add_ordered_field(f)

        elif self.record_type == 'xml':
            for field in re.findall(r'<controlfield tag="(.*?)">(.*?)</controlfield>', self.data, re.M):
                tag, data = field[0], field[1]
                subfields = []
                for s in re.findall(r'<subfield code="(.)">(.*?)</subfield>', data):
                    try: subfields.extend([s[0], s[1]])
                    except: pass
                f = Field(tag=tag, data=data)
                self.record.add_ordered_field(f)
            self.data = ''.join(line for line in self.data.split('\n'))
            for field in re.findall(r'<datafield tag="(.*?)" ind1="(.?)" ind2="(.?)">(.*?)</datafield>', self.data,
                                    re.M):
                tag, ind1, ind2, data = field[0], field[1], field[2], field[3]
                if ind1 == '': ind1 = ' '
                if ind2 == '': ind2 = ' '
                subfields = []
                for s in re.findall(r'<subfield code="(.)">(.*?)</subfield>', data):
                    try: subfields.extend([s[0], s[1]])
                    except: pass
                f = Field(tag=tag, indicators=[ind1, ind2], subfields=subfields)
                self.record.add_ordered_field(f)

        elif self.record_type == 'txt':
            for line in self.data.split('\n'):
                if line:
                    if '*** DOCUMENT BOUNDARY ***' in line:
                        continue
                    elif 'FORM=' in line:
                        f = Field(tag='FMT', indicators=[' ', ' '], subfields=['a', line.split('=', 1)[1].strip()])
                        self.record.add_ordered_field(f)
                    else:
                        tag = line[1:4]
                        try: test = int(tag)
                        except: test = None
                        if tag == '000' or (test and test < 10) or tag in ALEPH_CONTROL_FIELDS:
                            f = Field(tag=tag, data=line.split('|a', 1)[1].strip())
                        else:
                            ind1 = line[6]
                            ind2 = line[7]
                            subfields = []
                            for s in line.split('|')[1:]:
                                try: subfields.extend([s[0], s[1:]])
                                except: pass
                            f = Field(tag=tag, indicators=[ind1, ind2], subfields=subfields)
                        self.record.add_ordered_field(f)

    def as_marc(self):
        return self.record.as_marc()

    def as_xml(self):
        return self.record.as_xml()

    def __str__(self):
        return str(self.record)

    def identifier(self):
        try: return self.record['001'].data.replace('CKEY', '').strip()
        except: return None


class MARCReader(object):

    def __init__(self, marc_target):
        if hasattr(marc_target, 'read') and callable(marc_target.read):
            self.file_handle = marc_target

    def __iter__(self):
        return self

    def close(self):
        if self.file_handle:
            self.file_handle.close()
            self.file_handle = None

    def __next__(self):
        first5 = self.file_handle.read(5)
        if not first5: raise StopIteration
        if len(first5) < 5: raise RecordLengthError
        return MARCRecord(first5 + self.file_handle.read(int(first5) - 5))


class MARCWriter(object):
    def __init__(self, file_handle):
        self.file_handle = file_handle

    def write(self, record):
        if not isinstance(record, MARCRecord) and not isinstance(record, SAMIRecord):
            raise RecordWritingError
        self.file_handle.write(record.as_marc())

    def close(self):
        self.file_handle.close()
        self.file_handle = None


class MARCRecord(object):
    def __init__(self, data='', leader=' ' * LEADER_LENGTH):
        self.leader = '{}22{}4500'.format(leader[0:10], leader[12:20])
        self.fields = list()
        self.pos = 0
        if len(data) > 0: self.decode_marc(data)

    def __getitem__(self, tag):
        fields = self.get_fields(tag)
        if len(fields) > 0: return fields[0]
        return None

    def __contains__(self, tag):
        fields = self.get_fields(tag)
        return len(fields) > 0

    def __iter__(self):
        self.__pos = 0
        return self

    def __next__(self):
        if self.__pos >= len(self.fields): raise StopIteration
        self.__pos += 1
        return self.fields[self.__pos - 1]

    def __str__(self):
        fields, directory = b'', b''
        offset = 0

        for field in self.fields:
            field_data = field.as_marc()
            fields += field_data
            if field.tag.isdigit():
                directory += ('%03d' % int(field.tag)).encode('utf-8')
            else:
                directory += ('%03s' % field.tag).encode('utf-8')
            directory += ('%04d%05d' % (len(field_data), offset)).encode('utf-8')
            offset += len(field_data)

        directory += END_OF_FIELD.encode('utf-8')
        fields += END_OF_RECORD.encode('utf-8')
        base_address = LEADER_LENGTH + len(directory)
        record_length = base_address + len(fields)
        leader = '%05d%s%05d%s' % (record_length, self.leader[5:12], base_address, self.leader[17:])

        text_list = ['=LDR  {}'.format(leader)]
        text_list.extend([str(field) for field in self.fields])
        return '\n'.join(text_list) + '\n'

    def add_field(self, *fields):
        self.fields.extend(fields)

    def add_ordered_field(self, *fields):
        for f in fields:
            if len(self.fields) == 0 or not f.tag.isdigit():
                self.fields.append(f)
                continue
            self._sort_fields(f)

    def _sort_fields(self, field):
        tag = int(field.tag)

        i, last_tag = 0, 0
        for selff in self.fields:
            i += 1
            if not selff.tag.isdigit() and selff.tag not in ALEPH_CONTROL_FIELDS:
                self.fields.insert(i - 1, field)
                break

            if selff.tag not in ALEPH_CONTROL_FIELDS:
                last_tag = int(selff.tag)

            if last_tag > tag:
                self.fields.insert(i - 1, field)
                break
            if len(self.fields) == i:
                self.fields.append(field)
                break

    def get_fields(self, *args):
        if len(args) == 0: return self.fields
        return [f for f in self.fields if f.tag.upper() in args]

    def decode_marc(self, marc):
        # Extract record leader
        try:
            self.leader = marc[0:LEADER_LENGTH].decode('ascii')
        except:
            print('Record has problem with Leader and cannot be processed')
        if len(self.leader) != LEADER_LENGTH: raise LeaderError

        # Determine character encoding
        self.leader = self.leader[0:9] + 'a' + self.leader[10:]

        # Extract the byte offset where the record data starts
        base_address = int(marc[12:17])
        if base_address <= 0: raise BaseAddressError
        if base_address >= len(marc): raise BaseAddressLengthError

        # Extract directory
        # base_address-1 is used since the directory ends with an END_OF_FIELD byte
        directory = marc[LEADER_LENGTH:base_address - 1].decode('ascii')

        # Determine the number of fields in record
        if len(directory) % DIRECTORY_ENTRY_LENGTH != 0:
            raise DirectoryError
        field_total = len(directory) / DIRECTORY_ENTRY_LENGTH

        # Add fields to record using directory offsets
        field_count = 0
        while field_count < field_total:
            entry_start = field_count * DIRECTORY_ENTRY_LENGTH
            entry_end = entry_start + DIRECTORY_ENTRY_LENGTH
            entry = directory[entry_start:entry_end]
            entry_tag = entry[0:3]
            entry_length = int(entry[3:7])
            entry_offset = int(entry[7:12])
            entry_data = marc[base_address + entry_offset:base_address + entry_offset + entry_length - 1]

            # Check if tag is a control field
            if str(entry_tag) < '010' and entry_tag.isdigit():
                field = Field(tag=entry_tag, data=entry_data.decode('utf-8'))
            elif str(entry_tag) in ALEPH_CONTROL_FIELDS:
                field = Field(tag=entry_tag, data=entry_data.decode('utf-8'))

            else:
                subfields = list()
                subs = entry_data.split(SUBFIELD_INDICATOR.encode('ascii'))
                # Missing indicators are recorded as blank spaces.
                # Extra indicators are ignored.

                subs[0] = subs[0].decode('ascii') + '  '
                first_indicator, second_indicator = subs[0][0], subs[0][1]

                for subfield in subs[1:]:
                    if len(subfield) == 0: continue
                    try:
                        code, data = subfield[0:1].decode('ascii'), subfield[1:].decode('utf-8', 'strict')
                        subfields.append(code)
                        subfields.append(data)
                    except:
                        print('Error in subfield code in field {}'.format(entry_tag))
                field = Field(
                    tag=entry_tag,
                    indicators=[first_indicator, second_indicator],
                    subfields=subfields,
                )
            self.add_field(field)
            field_count += 1

        if field_count == 0: raise FieldsError

    def as_marc(self):
        fields, directory = b'', b''
        offset = 0

        for field in self.fields:
            field_data = field.as_marc()
            fields += field_data
            if field.tag.isdigit():
                directory += ('%03d' % int(field.tag)).encode('utf-8')
            else:
                directory += ('%03s' % field.tag).encode('utf-8')
            directory += ('%04d%05d' % (len(field_data), offset)).encode('utf-8')
            offset += len(field_data)

        directory += END_OF_FIELD.encode('utf-8')
        fields += END_OF_RECORD.encode('utf-8')
        base_address = LEADER_LENGTH + len(directory)
        record_length = base_address + len(fields)
        strleader = '%05d%s%05d%s' % (record_length, self.leader[5:12], base_address, self.leader[17:])
        leader = strleader.encode('utf-8')
        return leader + directory + fields

    def as_xml(self):
        xml = '\n\t<marc:record>'
        fields, directory = b'', b''
        offset = 0
        for field in self.fields:
            field_data = field.as_marc()
            fields += field_data
            if field.tag.isdigit():
                directory += ('%03d' % int(field.tag)).encode('utf-8')
            else:
                directory += ('%03s' % field.tag).encode('utf-8')
            directory += ('%04d%05d' % (len(field_data), offset)).encode('utf-8')
            offset += len(field_data)
        directory += END_OF_FIELD.encode('utf-8')
        fields += END_OF_RECORD.encode('utf-8')
        base_address = LEADER_LENGTH + len(directory)
        record_length = base_address + len(fields)
        leader = '%05d%s%05d%s' % (record_length, self.leader[5:12], base_address, self.leader[17:])
        xml += '\n\t\t<marc:leader>{}</marc:leader>'.format(leader)
        for field in self.fields:
            xml += '\n' + field.as_xml()
        return xml + '\n\t</marc:record>'


class Field(object):

    def __init__(self, tag, indicators=None, subfields=None, data=''):
        if indicators is None: indicators = []
        if subfields is None: subfields = []
        indicators = [str(x) for x in indicators]

        # Normalize tag to three digits
        self.tag = '%03s' % tag

        # Check if tag is a control field
        if self.tag < '010' and self.tag.isdigit():
            self.data = str(data)
        elif self.tag in ALEPH_CONTROL_FIELDS:
            self.data = str(data)
        else:
            self.indicator1, self.indicator2 = self.indicators = indicators
            self.subfields = subfields

    def __iter__(self):
        self.__pos = 0
        return self

    def __getitem__(self, subfield):
        subfields = self.get_subfields(subfield)
        if len(subfields) > 0: return subfields[0]
        return None

    def __contains__(self, subfield):
        subfields = self.get_subfields(subfield)
        return len(subfields) > 0

    def __next__(self):
        if not hasattr(self, 'subfields'):
            raise StopIteration
        while self.__pos + 1 < len(self.subfields):
            subfield = (self.subfields[self.__pos], self.subfields[self.__pos + 1])
            self.__pos += 2
            return subfield
        raise StopIteration

    def __str__(self):
        if self.is_control_field() or self.tag in ALEPH_CONTROL_FIELDS:
            text = '={}  {}'.format(self.tag, self.data.replace(' ', '#'))
        else:
            text = '={}  '.format(self.tag)
            for indicator in self.indicators:
                if indicator in (' ', '#'): text += '#'
                else: text += indicator
            text += ' '
            for subfield in self:
                text += '${}{}'.format(subfield[0], subfield[1])
        return text

    def get_subfields(self, *codes):
        """Accepts one or more subfield codes and returns a list of subfield values"""
        values = []
        for subfield in self:
            if len(codes) == 0 or subfield[0] in codes:
                values.append(str(subfield[1]))
        return values

    def add_subfield(self, code, value):
        self.subfields.append(code)
        self.subfields.append(clean_text(value))

    def is_control_field(self):
        if self.tag < '010' and self.tag.isdigit(): return True
        if self.tag in ALEPH_CONTROL_FIELDS: return True
        return False

    def as_marc(self):
        if self.is_control_field():
            return (self.data + END_OF_FIELD).encode('utf-8')
        marc = self.indicator1 + self.indicator2
        for subfield in self:
            marc += SUBFIELD_INDICATOR + subfield[0] + subfield[1]
        return (marc + END_OF_FIELD).encode('utf-8')

    def as_xml(self):
        if self.is_control_field():
            return '\t\t<marc:controlfield tag="{}">{}</marc:controlfield>'.format(self.tag, clean_text(self.data))
        xml = '\t\t<marc:datafield tag="{}" ind1="{}" ind2="{}">'.format(self.tag, self.indicator1, self.indicator2)
        for subfield in self:
            xml += '\n\t\t\t<marc:subfield code="{}">{}</marc:subfield>'.format(subfield[0], clean_text(subfield[1].strip()))
        return xml + '\n\t\t</marc:datafield>'


# ====================
#      Functions
# ====================


def line_to_field(field_content):
    field_content = field_content.strip()
    tag = field_content[0:3]
    try: test = int(tag)
    except: test = None
    if (test and test < 10) or tag in ALEPH_CONTROL_FIELDS or tag == '000':
        return Field(tag=tag, data=field_content.split('|a', 1)[1])
    subfields = []
    for s in field_content.split('|')[1:]:
        try: subfields.extend([s[0], s[1:]])
        except: pass
    return Field(tag=tag, indicators=[' ', ' '], subfields=subfields)