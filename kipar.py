#!/usr/bin/python2.7
import re       # re.compile(), re.sub(), re.VERBOSE
import codecs   # codecs.open()
import sys      # sys.argv() and sys.exit()
import getopt   # getopt.getopt(), getopt.GetoptError
import MySQLdb  # MySQLdb.connect(), mysqldb.cursor()
import getpass  # getpass.getpass()


def main(argv):
    infile = "My Clippings.txt"
    # -i infile should be the only command line argument we need
    try:
        opts, args = getopt.getopt(argv, "i:")
    except getopt.GetoptError:
        print "kipar -i <infile>"
        sys.exit()
    for opt, arg in opts:
        if opt == "-i":
            infile = arg
    uploadClippings(infile)


def uploadClippings(infile):
    # connect to mysql w/out cleartext password!
    pw = getpass.getpass()
    try:
        mysqldb = MySQLdb.connect(host="localhost",
                                  user="bo",
                                  passwd=pw,
                                  db="library")
    except:
        print "error connecting to database"
        sys.exit()
    cursor = mysqldb.cursor()
    # which books are already in my library? Let's find out!
    library_index = []
    try:
        # TODO: remove any books from the index that don't actually exist
        # if the `index` table doesn't exist yet, make it exist!
        cursor.execute("SHOW TABLES LIKE \"index\";")
        res = cursor.fetchall()
        if len(res) == 0:
            cursor.execute("""CREATE TABLE `index` (
            ID int UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
            Title tinytext, Author tinytext);
            """)
        cursor.execute("SELECT Title, Author FROM `index`;")
        res = cursor.fetchall()
        for t in res:
            library_index.append(t[0] + " by " + t[1])
    except:
        print "error getting library data"
        sys.exit()
    # loop through the input file
    with codecs.open(infile, mode='r', encoding="UTF-8") as fin:
        while True:
            title = parseTitle(smart_read(fin))
            currBook = title[0] + " by " + title[1]
            # if we can't parseTitle, we're done
            if title == "Fatal error: couldn't parse Title...":
                break
            # if this book isn't in our library yet, add it
            # TODO: if it's in library_index but the table is gone, add table
            if currBook not in library_index:
                library_index.append(currBook)
                newBook(title, cursor)
            loc = parseLocation(smart_read(fin))
            content = ""
            while True:
                temp = parseContent(smart_read(fin))
                if temp is True:
                    break
                if temp is False:
                    # TODO: why is this an error again???
                    print "error, unexpected end of file"
                    return
                else:
                    content = content +\
                        temp.replace('\r\n', '').replace('\r', '')
            if loc[0] == "Highlight":
                Highlight(title[0], loc[1], loc[2], content, cursor, mysqldb)
            elif loc[0] == "Note":
                Note(title[0], loc[1], content, cursor, mysqldb)


# linux uses '\r\n' as line breaks, windows uses '\r' then '\r\n'
# account for this when reading lines
def smart_read(fin):
    output = fin.readline()
    while output == '\r\n' or output == '\r':
        output = fin.readline()
    return output


def parseContent(strinput):
    if strinput == "==========\r\n" or strinput == "==========\r":
        return True
    # this catches the end of the file
    if strinput == "":
        return False
    else:
        return cleanup(strinput)


def parseTitle(strinput):
    strinput = cleanup(strinput)
    # sample strinput:
    # ???Smarts: The Art (Science?) of Work (Allen, David; Gates, Bill)
    div = strinput.rfind('(')
    title = strinput[:div]
    author = strinput[div:]
    # sample title: """???Smarts: The Art (Science?) of Work """
    pattern = """
    ([\w '-]+)  # matches the title
    ,?          # there might be a subtitle separated by a comma
    :?          # or the subtitle might be separated by a colon
    [\w -]*     # subtitle
    """
    match = re.compile(pattern, re.VERBOSE).match(title)
    if match:
        title = match.group(1).strip().replace("'", "")
    else:
        return "Fatal error: couldn't parse Title..."
    # sample author: "(Allen, David; Gates, Bill)\n"
    # sample author: "(Unknown)\n"
    pattern = """
    \(          # start of the author chunk
    ([\w. ]+)   # author last name (or only name?)
    ,?\s?       # author separator
    ([\w. ]+)?  # author first name
    ;?          # coauthor separator
    ([\w. ]+)?  # coauthor last name
    ,?\s?       # coauthor separator
    ([\w. ]+)?  # coauthor first name
    \)          # end of the author chunk
    """
    match = re.compile(pattern, re.VERBOSE).search(author)
    if match:
        author_tuple = match.groups()
    else:
        return [title, "Unknown"]
    # the author might night have a first name
    if author_tuple[1] is None:
        author = author_tuple[0]
    else:
        author = author_tuple[1] + " " + author_tuple[0]
    # add the additional author if available
    if author_tuple[3] is None:
        addAuthor = author_tuple[2]
    elif author_tuple[2] is not None and author_tuple[3] is not None:
        addAuthor = author_tuple[3] + " " + author_tuple[2]
    return [title, author, addAuthor]


def parseLocation(strinput):
    strinput = cleanup(strinput)
    # sample strinputs:
    # - Your Highlight on page 12 | Location 550-551 | Added whenever...
    # - Your Highlight on Location 550-551 | Added whenever...
    # - Your Note on Location 1043 | Added whenever
    # - Your Note on page 139 | Location 1517 | Added
    pattern = """
    ^-\sYour\s       # matches the beginning of location lines
    (\w+?)           # content type (ie Highlight, Bookmark, Note)
    \son\s           # filler, always matches " on "
    (page|Location)  # does this line contain a page number?
    \s(\d+)-?        # page number OR location number
    (\d*)            # second location number if it exists
    \s\|\s           # filler, always matches " | "
    (Location|Added) # If there's still data here, it'll be Location data
    \s(\d*)-?        # first location number if it exists
    (\d*)            # second location number if it exists
    """
    match = re.compile(pattern, re.VERBOSE).match(strinput)
    if match:
        loc_tuple = match.groups()
        if loc_tuple[0] == "Highlight":
            if loc_tuple[1] == "Location":
                return [loc_tuple[0], int(loc_tuple[2]),
                        int(loc_tuple[3]), None]
            elif loc_tuple[1] == "page":
                return [loc_tuple[0], int(loc_tuple[5]),
                        int(loc_tuple[6]), int(loc_tuple[2])]
        else:
            if loc_tuple[1] == "Location":
                return [loc_tuple[0], int(loc_tuple[2]), None]
            elif loc_tuple[1] == "page" and loc_tuple[4] == "Location":
                return [loc_tuple[0], int(loc_tuple[5]), int(loc_tuple[2])]
            # what the fuck why is there ever a page number w/out location?
            elif loc_tuple[1] == "page" and loc_tuple[4] == "Added":
                return [loc_tuple[0], 0, None]
    else:
        print "Fatal error: couldn't parse Location...", repr(strinput)
        sys.exit()


# let's dumb down kindle's fancy characters
def cleanup(strinput):
    strinput = strinput.replace(u'\u2014', '-')
    strinput = strinput.replace(u'\u2013', '-')
    strinput = strinput.replace(u'\u2018', "'")
    strinput = strinput.replace(u'\u2019', "'")
    strinput = strinput.replace(u'\u201c', '"')
    strinput = strinput.replace(u'\u201d', '"')
    strinput = strinput.replace(u'\ufeff', '')
    # anything not caught above can just be removed
    return re.sub('[^\n\r -~]', '', strinput)


# create a new table + new row in `index` given a new book
# newBook is only called if this title is not in the index yet
# all titles in the index also have an associated table.
def newBook(title_tuple, cursor):
    # add new row to `index`
    title_tuple[0]
    newRowQuery = """
    INSERT INTO `index`
    (Title, Author)
    VALUES ('%(title)s', '%(author)s');""" % {
        "title": title_tuple[0],
        "author": title_tuple[1]}
    # print newRowQuery
    # create new table
    newTableQuery = """
    CREATE TABLE `%(table_tit)s` (
    Start int PRIMARY KEY, End int, Highlight text, Note text, Page int);
    """ % {"table_tit": title_tuple[0].replace(" ", "_").
           replace("-", "_").lower()}
    # print newTableQuery
    try:
        cursor.execute(newRowQuery)
    except:
        print "Error adding new row to `index`:", newRowQuery
        sys.exit()
    try:
        cursor.execute(newTableQuery)
    except:
        print "Error adding new table to MySQL db", newTableQuery
        sys.exit()


def Highlight(title, start, end, highlight, cursor, db):
    highlight = highlight.replace("\"", "\\\"").replace("\'", "\\\'")
    title = title.replace(" ", "_").replace("-", "_").lower()
    # select highlights/notes that begin within the current highlight
    probe = """SELECT * FROM `%(title)s`
    where Start>=%(start)d and Start<=%(end)d;""" % {
        "title": title,
        "start": start,
        "end": end}
    res = ()
    try:
        cursor.execute(probe)
        res = cursor.fetchall()
    except:
        print "Error accessing table:", probe
    # if we get an empty set back, add the highlight
    # or if we get something back with end = highlight = NULL,
    #   then we're probably looking at a note, add the highlight here
    if len(res) == 0:
        newHighlight(title, start, end, highlight, cursor, db)
    elif len(res) == 1 and res[0][2] is None:
        addHighlight(title, res[0][0], start, end, highlight, cursor, db)
    # elif len(res) == 2:
        # print "len(res) == 2", res, "\n\n"


def newHighlight(title, start, end, highlight, cursor, db):
    query = """
    INSERT INTO %(title)s
    (Start, End, Highlight)
    VALUES (%(start)d, %(end)d, '%(highlight)s');
    """ % {
        "title": title,
        "start": start,
        "end": end,
        "highlight": highlight}
    try:
        cursor.execute(query)
        db.commit()
    except:
        print "Error highlight data to table:", query


def addHighlight(title, loc, start, end, highlight, cursor, db):
    query = """
    UPDATE %(title)s
    SET Start='%(start)d',
    End='%(end)d',
    Highlight='%(highlight)s'
    WHERE Start=%(loc)d;
    """ % {
        "title": title,
        "start": start,
        "end": end,
        "highlight": highlight,
        "loc": loc}
    try:
        cursor.execute(query)
        db.commit()
    except:
        print "Error creating new highlight:", query


def Note(title, loc, note, cursor, db):
    note = note.replace("\"", "\\\"").replace("\'", "\\\'")
    title = title.replace(" ", "_").replace("-", "_").lower()
    # select highlights/notes that begin within the current highlight
    probe = """SELECT * FROM `%(title)s` WHERE
    (Start<=%(loc)d and End>=%(loc)d) or
    Start=%(loc)d;""" % {
        "title": title,
        "loc": loc}
    res = ()
    try:
        cursor.execute(probe)
        res = cursor.fetchall()
    except:
        print "Error accessing table:", probe, "\n"
    if len(res) == 0:
        newNote(title, loc, note, cursor, db)
    elif len(res) == 1 and res[0][3] is None:
        addNote(title, res[0][0], note, cursor, db)
    # elif len(res) == 2:
        # print "len(res) == 2", res, "\n\n"


def newNote(title, loc, note, cursor, db):
    query = """
    INSERT INTO %(title)s
    (Start, Note)
    VALUES (%(start)d, '%(note)s');
    """ % {
        "title": title,
        "start": loc,
        "note": note}
    # print query
    try:
        cursor.execute(query)
        db.commit()
    except:
        print "Error creating new note:", query


def addNote(title, loc, note, cursor, db):
    query = """
    UPDATE %(title)s SET Note='%(note)s' WHERE Start=%(start)d;
    """ % {
        "title": title,
        "note": note,
        "start": loc}
    # print query
    try:
        cursor.execute(query)
        db.commit()
    except:
        print "Error adding note to table:", query


if __name__ == "__main__":
    main(sys.argv[1:])


# TODO:
# "title": title[0].replace(" ", "_").replace("-", "_"),
# with some kind of regular expression