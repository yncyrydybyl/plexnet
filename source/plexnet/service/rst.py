r"""
================
reStructuredText
================

reStructuredText is an easy to use markup language for plain text content. This
module provides a core utility function called ``render_rst`` which converts rST
into XHTML or LaTeX output formats.

  >>> text = '''
  ...
  ... This is a **test** document.
  ...
  ... '''

By default the output format of 'xhtml' is assumed:

  >>> render_rst(text)
  u'<p>This is a <strong>test</strong> document.</p>'

You can also pass in the alternative format of 'tex':

  >>> render_rst(text, format='tex')
  u'\n\\setlength{\\locallinewidth}{\\linewidth}\n\nThis is a \\textbf{test} document.\n'

This produces TeX output which should be run through an application like
``latex`` or ``pdflatex`` to get a typeset document.

By default the input is assumed to be either a unicode object or a str object
encoded as 'utf-8'. You can specify an alternative input encoding if needed:

  >>> text = '''
  ...
  ... Price in Caf\xe9s are often in \x80
  ...
  ... '''

  >>> render_rst(text, encoding='windows-1252')
  u'<p>Price in Caf\xe9s are often in \u20ac</p>'

The output is always a unicode object which can then be decoded into other
codecs if needed.

Let's look at a sample text with a few more elements:

  >>> text = '''
  ...
  ... ==============
  ... Some Big Title
  ... ==============
  ...
  ... Yet Another Title
  ... -----------------
  ...
  ... :Author: tav
  ... :Some-Field: some value
  ...
  ... Hello *world*!
  ...
  ... '''

You can set the optional ``as_whole`` parameter to True and a complete HTML or
LaTeX output will be generated with default headers and footers:

  >>> render_rst(text, as_whole=True)
  u'<?xml...<html...<p>Hello <em>world</em>!</p>\n</div>\n</body>\n</html>'

As opposed to just the rendered version of the text itself:

  >>> render_rst(text)
  u'<p>Hello <em>world</em>!</p>'

If you want the data in the bibliographic fields, you can get it by specifying
the optional ``with_docinfo`` parameter:

  >>> print render_rst(text, with_docinfo=True)
  <div class="docinfo">
  <table class="docinfo" frame="void" rules="none">
  <col class="docinfo-name" />
  <col class="docinfo-content" />
  <tbody valign="top">
  <tr><th class="docinfo-name">Author:</th>
  <td>tav</td></tr>
  <tr class="field"><th class="docinfo-name">Some-Field:</th><td class="field-body">some value</td>
  </tr>
  </tbody>
  </table>
  <BLANKLINE>
  </div>
  <div class="document">
  <p>Hello <em>world</em>!</p>
  </div>

If the bibliographic data is needed as a dictionary, then the optional
``with_props`` parameter can be specified:

  >>> output, props = render_rst(text, with_props=True)

  >>> output
  u'<p>Hello <em>world</em>!</p>'

  >>> sorted(props.keys())
  [u'author', u'some-field', u'subtitle', u'title']

As can be seen, this includes the bibliographic fields as well as the extracted
text title and subtitle:

  >>> props['author']
  u'tav'

  >>> props['some-field']
  u'some value'

  >>> props['title']
  u'Some Big Title'

  >>> props['subtitle']
  u'Yet Another Title'

The HTML output has a number of typographic additions like smart quotes and em
dashes:

  >>> text = '''
  ...
  ... "This is a quote" -- Gandhi
  ...
  ... '''

  >>> render_rst(text)
  u'<p>&ldquo;This is a quote&rdquo; &mdash; Gandhi</p>'

And, finally, in addition to the default directives, a ``syntax`` directive has
been added which allows for the syntax highlighting of included source code in a
variety of languages.

  >>> text = '''
  ...
  ... This is some text
  ...
  ... .. syntax:: python
  ...
  ...     double = lambda x: 2 * x
  ...
  ... '''

  >>> print render_rst(text)
  <p>This is some text</p>
  <div class="syntax"><pre>...<span class="k">lambda</span>...</pre></div>

"""

import os
import re
import sys

from string import punctuation as PUNCTUATION
from time import time

from docutils import nodes
from docutils.frontend import OptionParser
from docutils.io import FileInput
from docutils.parsers.rst import directives, Directive, DirectiveError, Parser
from docutils.parsers.rst.states import RSTStateMachine, state_classes
from docutils.readers.standalone import Reader
from docutils.transforms import writer_aux, universal, references, frontmatter
from docutils.transforms import misc
from docutils.writers.html4css1 import HTMLTranslator, Writer as HTMLWriter
from docutils.writers.latex2e import LaTeXTranslator, Writer as LaTexWriter
from docutils.utils import relative_path, new_document

from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name, TextLexer

from ..util.io import IteratorParser

# ------------------------------------------------------------------------------
# some konstants
# ------------------------------------------------------------------------------

HTML_VISITOR_ATTRIBUTES = (
    'head_prefix', 'head', 'stylesheet', 'body_prefix',
    'body_pre_docinfo', 'docinfo', 'body', 'body_suffix',
    'title', 'subtitle', 'header', 'footer', 'meta', 'fragment',
    'html_prolog', 'html_head', 'html_title', 'html_subtitle',
    'html_body'
    )

LATEX_VISITOR_ATTRIBUTES = (
    "head_prefix", "head", "body_prefix", "body", "body_suffix"
    )

DEFAULT_TRANSFORMS = [

    universal.Decorations,
    universal.ExposeInternals,
    universal.StripComments,

    references.Substitutions,
    references.PropagateTargets,
    frontmatter.DocTitle,
    frontmatter.SectionSubTitle,
    frontmatter.DocInfo,
    references.AnonymousHyperlinks,
    references.IndirectHyperlinks,
    references.Footnotes,
    references.ExternalTargets,
    references.InternalTargets,
    references.DanglingReferences,
    misc.Transitions,

    ]

HTML_TRANSFORMS = DEFAULT_TRANSFORMS + [

    universal.Messages,
    universal.FilterMessages,
    universal.StripClassesAndElements,

    writer_aux.Admonitions,

    ]

OPTION_PARSER = OptionParser((Parser, Reader))
HTML_OPTION_PARSER = OptionParser((Parser, Reader, HTMLWriter))
LATEX_OPTION_PARSER = OptionParser((Parser, Reader, LaTexWriter))

HTML_SETUP = ('html', HTMLTranslator, HTML_TRANSFORMS, HTML_OPTION_PARSER)
LATEX_SETUP = ('tex', LaTeXTranslator, DEFAULT_TRANSFORMS, LATEX_OPTION_PARSER)
RAW_SETUP = (None, None, DEFAULT_TRANSFORMS, OPTION_PARSER)

# ------------------------------------------------------------------------------
# some pre-kompiled regular expressions
# ------------------------------------------------------------------------------

replace_toc_attributes = re.compile(
    '(?sm)<p class="topic-title(.*?)"><a name="(.*?)">(.*?)</a></p>(.*?)</div>'
    ).sub

replace_drop_shadows = re.compile(
    '(?sm)<div class="figure(.*?)<p><img(.*?)/></p>(.*?)</div>'
    ).sub

replace_abstract_attributes = re.compile('<div class="abstract topic">').sub
replace_ampersands = re.compile('&(?![^\s&]*;)').sub
replace_comments = re.compile(r'(?sm)\n?\s*<!--(.*?)\s-->\s*\n?').sub
replace_plexlinks = re.compile('(?sm)\[\[(.*?)\]\]').sub
replace_title_headings = re.compile('(?sm)<h1 class="title">(.*?)</h1>').sub
replace_whitespace = re.compile('[\v\f]').sub

split_html_tags = re.compile('(?sm)<(.*?)>').split

# ------------------------------------------------------------------------------
# rst direktives
# ------------------------------------------------------------------------------

def imap_directive(name, arguments, options, content, lineno,
                   content_offset, block_text, state, state_machine):
    """Render an image <map> element."""

    encoding = options.get('encoding', state.document.settings.input_encoding)

    image_alt = options.get('alt', '')
    image_class = options.get('class', '')

    attributes['source'] = imap_source = arguments[0]

    source_dir = os.path.dirname(
        os.path.abspath(state.document.current_source)
        )

    path = os.path.normpath(os.path.join(source_dir, imap_source))
    path = relative_path(None, path)

    try:
        state.document.settings.record_dependencies.add(path)
        raw_file = FileInput(
            source_path=path, encoding=encoding,
            error_handler=state.document.settings.input_encoding_error_handler,
            handle_io_errors=None)
    except IOError, error:
        severe = state_machine.reporter.severe(
            'Problems with "%s" directive path:\n%s.' % (name, error),
            nodes.literal_block(block_text, block_text), line=lineno)
        return [severe]

    text = raw_file.read().replace(
        'ALT-GOES-HERE', image_alt).replace(
        'CLASS-GOES-HERE', image_class)

    raw_node = nodes.raw('', text, format='html')
    return [raw_node]

imap_directive.arguments = (1, 0, False)
                           # (required, optional, is-spaces-allowed-in-last)
imap_directive.options = {
    'alt': directives.unchanged,
    'class': directives.class_option
    }
imap_directive.content = False

# @/@ disabled till it's abstrakted further and sekurity cheked
# directives.register_directive('imap', imap_directive)

def break_directive(name, arguments, options, content, lineno,
                    content_offset, block_text, state, state_machine):
    """Render an HTML break element."""

    if arguments:
        break_class = arguments[0]
    else:
        break_class = 'clear'

    raw_node = nodes.raw('', '<hr class="%s" />' % break_class, format='html')

    # return [nodes.transition()]
    return [raw_node]

break_directive.arguments = (0, 1, True)
break_directive.options = {
    'class':directives.class_option
    }
break_directive.content = False

directives.register_directive('break', break_directive)

# ------------------------------------------------------------------------------
# a tag direktive!!
# ------------------------------------------------------------------------------

SEEN_TAGS_CACHE = None
TAG_COUNTER = None

class TagDirective(Directive):
    """Convert tags into HTML annotation blocks."""

    required_arguments = 0
    optional_arguments = 1
    final_argument_whitespace = True

    has_content = True

    def run(self, tag_cache={}):

        if not self.content:
            return []

        if self.arguments:
            arguments = self.arguments[0].strip().split(',')
        else:
            arguments = []

        tag_list_id = CURRENT_PLAN_ID or 'list'

        output = []; add = output.append
        tag_id = None

        for tag in arguments:

            if tag in tag_cache:
                add(tag_cache[tag])
                continue

            ori_tag = tag
            tag = tag.strip().rstrip(u',').strip()

            if not tag:
                continue

            if tag.startswith('id:'):
                tag_id = tag[3:]
                continue

            if tag.startswith('@'):
                tag_class = u'-'.join(tag[1:].lower().split())
                tag_type = 'zuser'
                tag_text = tag
            elif tag.startswith('#'):
                tag_class = u'-'.join(tag[1:].lower().split())
                tag_type = '2'
                tag_text = tag
            elif ':' in tag:
                tag_split = tag.split(':', 1)
                if len(tag_split) == 2:
                    tag_type, tag_text = tag_split
                else:
                    tag_type = tag_split[0]
                    tag_text = u""
                tag_type = tag_type.strip().lower()
                if tag_type == 'dep' and ':' not in tag_text:
                    tag_class = u'dep-%s-%s' % (CURRENT_PLAN_ID, tag_text)
                else:
                    tag_class = u'-'.join(tag.replace(':', ' ').lower().split())
            else:
                tag_class = u'-'.join(tag.lower().split())
                tag_type = '1'
                tag_text = tag.upper()

            if ':' in tag:
                lead = tag.split(':', 1)[0]
                tag_name = '%s:%s' % (lead.lower(), tag_text)
            else:
                tag_name = tag_text

            tag_span = (
                u'<span class="tag tag-type-%s tag-val-%s" tagname="%s" tagnorm="%s">%s</span> ' %
                (tag_type, tag_class, tag_name, tag.lower(), tag_text)
                )

            tag_cache[ori_tag] = tag_span
            add(tag_span)

        output.sort()

        if not tag_id:
            global TAG_COUNTER
            TAG_COUNTER = TAG_COUNTER + 1
            tag_id = 'temp-%s' % TAG_COUNTER

        tag_id = '%s-%s' % (tag_list_id, tag_id)

        if tag_id in SEEN_TAGS_CACHE:
            raise DirectiveError(2, "The tag id %r has already been used!" % tag_id)

        SEEN_TAGS_CACHE.add(tag_id)

        if not output:
            pass
            # add(u'<span class="tag tag-untagged"></span>')

        output.append(u'<a class="tag-link" href="#tag-ref-%s-main">&middot;</a>' % tag_id)
        output.insert(
            0, (u'<div class="tag-segment" id="tag-ref-%s">' % tag_id)
            )

        add(u'</div>')

        tag_info = nodes.raw('', u''.join(output), format='html')
        tag_content_container = nodes.bullet_list(
            ids=['tag-ref-%s-content' % tag_id]
            )

        tag_content = nodes.list_item()
        self.state.nested_parse(self.content, self.content_offset, tag_content)

        tag_content_container += tag_content

        prefix = nodes.raw('', u'<div id="tag-ref-%s-main" class="tag-content">' % tag_id, format='html')
        suffix = nodes.raw('', u'</div>', format='html')

        return [prefix, tag_content_container, tag_info, suffix]

directives.register_directive('tag', TagDirective)

# ------------------------------------------------------------------------------
# plan direktive!
# ------------------------------------------------------------------------------

CURRENT_PLAN_ID = None

def plan_directive(name, arguments, options, content, lineno,
                   content_offset, block_text, state, state_machine):
    """Setup for tags relating to a plan file."""

    global CURRENT_PLAN_ID

    if not CURRENT_PLAN_ID:
        raw_node = nodes.raw(
            '',
            '<div id="plan-container"></div>'
            '<script type="text/javascript" src="static/plan.js"></script>'
            '<hr class="clear" />',
            format='html'
            )
    else:
        raw_node = nodes.raw('', '', format='html')

    CURRENT_PLAN_ID = arguments[0]

    return [raw_node]

plan_directive.arguments = (1, 0, True)
plan_directive.options = {}
plan_directive.content = False

directives.register_directive('plan', plan_directive)

# ------------------------------------------------------------------------------
# konvert plain kode snippets to funky html
# ------------------------------------------------------------------------------

SYNTAX_FORMATTER = HtmlFormatter(cssclass='syntax', lineseparator='<br/>')

def syntax_directive(name, arguments, options, content, lineno,
                     content_offset, block_text, state, state_machine):
    """Prettify <syntax> snippets into marked up HTML blocks."""

    try:
        lexer = get_lexer_by_name(arguments[0])
    except ValueError:
        lexer = TextLexer()

    return [nodes.raw(
        '',
        highlight(u'\n'.join(content), lexer, SYNTAX_FORMATTER),
        format='html'
        )]

syntax_directive.arguments = (1, 0, False)
syntax_directive.options = {
    'format': directives.unchanged
    }
syntax_directive.content = True

directives.register_directive('syntax', syntax_directive)

def doctest2html(content):
    """Convert doctest strings to CSS'd HTML."""

    out = []

    for line in content.splitlines():
        if line.startswith('&gt;&gt;&gt;') or line.startswith('...'):
            line = '<span class="doctest-input">' + line + '</span>'
        elif line:
            line = '<span class="doctest-output">' + line + '</span>'
        out.append(line)

    return '\n'.join(out)

# ------------------------------------------------------------------------------
# pretty typographical syntax converter
# ------------------------------------------------------------------------------

def convert(content):
    """Convert certain characters to prettier typographical syntax."""

    # remember: the order of the replacements matter...

    content = content.replace(
        # '&lt;', '<').replace(
        # '&gt;', '>').replace(
        '&quot;', '"').replace(
        # '&amp;', '&').replace(
        ' -->', 'HTML-COMMENT-ELEMENT-CLOSE').replace(
        '-&gt;', '&rarr;').replace(
        '<-', '&larr;').replace(
        '---', '&ndash;').replace(
        '--', '&mdash;').replace(
        '<<', '&laquo;').replace(
        '>>', '&raquo;').replace(
        '(C)','&copy;').replace(    # hmz, why am i promoting ipr? ;p
        '(c)','&copy;').replace(
        '(tm)','&trade;').replace(
        '(TM)','&trade;').replace(
        '(r)','&reg;').replace(
        '(R)','&reg;').replace(
        '...', '&#8230;').replace(
        'HTML-COMMENT-ELEMENT-CLOSE', ' -->')

    icontent = IteratorParser(content)
    content = []

    _scurly = _dcurly = False
    _space = True
    _apply = False

    index = 0
    prev = ''

    while True:

        try:
            char = icontent.next()
        except StopIteration:
            break

        if not (_scurly or _dcurly) and _space:
            if char == "'":
                _scurly = index + 1
            elif char == '"':
                _dcurly = index + 1

        if _scurly and (_scurly != index + 1) and char == "'" and prev != '\\':
            try:
                n = icontent.next()
                if n in PUNCTUATION or n.isspace():
                    _apply = True
                icontent.push(n)
            except:
                _apply = True
            if _apply:
                content[_scurly - 1] = '&lsquo;'
                char = '&rsquo;'
                _scurly = False
            _apply = False
        
        if _dcurly and (_dcurly != index + 1) and char == '"' and prev != '\\':
            try:
                n = icontent.next()
                if n in PUNCTUATION or n.isspace():
                    _apply = True
                icontent.push(n)
            except:
                _apply = True
            if _apply:
                content[_dcurly - 1] = '&ldquo;'
                char = '&rdquo;'
                _dcurly = False
            _apply = False

        content.append(char)
        prev = char
        index += 1
        
        if char.isspace():
            _space = True
        else:
            _space = False

    content = ''.join(content).replace('"', '&quot;')
    content = replace_plexlinks(render_plexlink, content)

    # perhaps === heading === stylee ?

    return content

# ------------------------------------------------------------------------------
# the meta prettifier funktion which kalls the above ones
# ------------------------------------------------------------------------------

def escape_and_prettify(content):
    """Escape angle brackets appropriately and prettify certain blocks."""

    # our markers and our output gatherer

    _literal_block = _element = _content = False
    output = []

    for i, block in enumerate(split_html_tags(content.strip())):

        # we setup the state

        if i % 2:

            _content = False
            _element = True

            if _literal_block and (_literal_block[1] == block):
                _literal_block = False

            if block == 'tt class="literal"':
                _literal_block = ('tt', '/tt')
            elif block in ['pre',
                           'pre class="literal-block"',
                           'pre class="last literal-block"',
                           'pre class="code"']:
                _literal_block = ('pre', '/pre')
            elif block in ['span class="pre"']:
                _literal_block = ('span', '/span')
            elif block == 'pre class="doctest-block"':
                _literal_block = ('doctest', '/pre')
            elif block == 'style type="text/css"':
                _literal_block = ('style type="text/css"', '/style')
            elif block == 'script type="text/javascript"':
                _literal_block = ('script type="text/javascript"', '/script')

        else:

            _content = True
            _element = False

        # we do different things based on the state

        if _element:
            output.append('<' + block + '>')
        elif _content:
            if _literal_block:
                if _literal_block[0] == 'doctest':
                    output.append(doctest2html(block))
                else:
                    output.append(block)
            else:
                output.append(convert(block))

    output = ''.join(output)

    # gah!
    output = output.replace('<<', '&lt;<')

    # praise be to them negative lookahead regex thingies
    output = replace_ampersands('&amp;', output)

    return output

# ------------------------------------------------------------------------------
# some utility funktions
# ------------------------------------------------------------------------------

def render_drop_cap(content):
    """Render the first character as a drop capital"""

    content = content.groups()[0]

    if content:
        if len(content) >= 2:
            return '<p><span class="dropcap">' + content[0] + \
                   '</span>'  + content[1:]

    return '<p></p>'

def render_plexlink(content):
    """Render [[plexlinks]]."""

    name = content.groups()[0]

    if '|' in name:
        name, linkname = name.split('|', 1)
    else:
        linkname = name

    return u'<a href="%s.html">%s</a>' % (u'-'.join(name.split()), linkname)

# ------------------------------------------------------------------------------
# parse the :properties: included in a document
# ------------------------------------------------------------------------------

def parse_headers(source_lines, props, toplevel=False):
    """Parse the metadata stored in the content headers."""

    new_data = []; out = new_data.append
    iterative_source = IteratorParser(source_lines)

    for line in iterative_source:

        if line.startswith(':') and line.find(':', 2) != -1:

            marker = line.find(':', 2)
            prop, value = line[1:marker], line[marker+1:].strip()

            if prop.lower().startswith('x-'):
                _strip_prop = True
            else:
                _strip_prop = False

            if not _strip_prop:
                out(line)

            while True:
                try:
                    line = iterative_source.next()
                    if not _strip_prop:
                        out(line)
                except:
                    break
                sline = line.strip()
                if sline and not (sline.startswith(':') and \
                                  sline.find(':', 2) != -1):
                    value += ' ' + sline
                else:
                    iterative_source.push(line)
                    if not _strip_prop:
                        del new_data[-1]
                    break

            prop = prop.lower()

            if prop in props:
                oldvalue = props[prop]
                if isinstance(oldvalue, list):
                    oldvalue.append(value)
                else:
                    props[prop] = [oldvalue, value]
            else:
                props[prop] = value

        else:
            out(line)

    # re.sub('(?sm)\[\[# (.*?)\]\]', render_includes, content)
    return new_data, props

# ------------------------------------------------------------------------------
# our kore renderer
# ------------------------------------------------------------------------------

def render_rst(
    source, format='xhtml', encoding='utf-8', with_props=False,
    with_docinfo=False, as_whole=False
    ):
    """Return the rendered ``source`` with optional extracted properties."""

    global SEEN_TAGS_CACHE, TAG_COUNTER, CURRENT_PLAN_ID
    SEEN_TAGS_CACHE = set()
    TAG_COUNTER = 0
    CURRENT_PLAN_ID = None

    if format in ('xhtml', 'html'):
        format, translator, transforms, option_parser = HTML_SETUP
    elif format in ('tex', 'latex'):
        format, translator, transforms, option_parser = LATEX_SETUP
    elif format == 'raw':
        format, translator, transforms, option_parser = RAW_SETUP
    else:
        raise ValueError("Unknown format: %r" % format)

    settings = option_parser.get_default_values()
    settings._update_loose({
        'footnote_references': 'superscript', # 'mixed', 'brackets'
        'halt_level': 6,
        # 'report_level': 2,
        'trim_footnote_reference_space': 1,
        })

    document = new_document('[dynamic-text]', settings)

    if not isinstance(source, unicode):
        source = unicode(source, encoding)

    source = replace_whitespace(' ', source)
    source_lines = [s.expandtabs(4).rstrip() for s in source.splitlines()]

    if with_props:
        source_lines, props = parse_headers(source_lines, {}, True)

    document.reporter.attach_observer(document.note_parse_message)

    RSTStateMachine(
        state_classes=state_classes,
        initial_state='Body',
        ).run(source_lines, document)

    document.reporter.detach_observer(document.note_parse_message)
    document.current_source = document.current_line = None

    document.transformer.add_transforms(transforms)
    document.transformer.apply_transforms()

    if not format:
        return unicode(document)

    visitor = translator(document)
    document.walkabout(visitor)

    # see HTML_VISITOR_ATTRIBUTES/LATEX_VISITOR_ATTRIBUTES to see other attrs

    if as_whole:
        output = visitor.astext()
    else:
        if format == 'html' and with_docinfo:
            output = (
                u'<div class="docinfo">\n%s\n</div>\n<div class="document">\n%s</div>'
                % (u''.join(visitor.docinfo), u''.join(visitor.body))
                )
        else:
            output = u''.join(visitor.body)

    # post rst-konversion prosessing

    if format == 'html':

        # [[plexlinks]]
        # output = re.sub(
        #     '(?sm)\[\[(.*?)\]\]',
        #     render_plexlink,
        #     output)

        # syntax highlighting for kode snippets
        # output = re.sub(
        #     '(?sm)<p>(?:\s)?&lt;code class=&quot;(.*?)&quot;&gt;(?::)?</p>(?:\n<blockquote>)?\n<pre class="literal-block">(.*?)</pre>(?:\n</blockquote>)?\n<p>(?:\s)?&lt;/code&gt;</p>',
        #     code2html,
        #     output)

        # support for embedding html into rst dokuments and prettifikation
        output = escape_and_prettify(output)

        # toc href id and div adder
        output = replace_toc_attributes(
            '<p class="topic-title\\1"><a name="\\2"></a><span id="document-toc">\\3</span></p>\n<div id="document-toc-listing">\\4</div></div>',
            output)

        # inserting an "#abstract" id
        output = replace_abstract_attributes(
            r'<div id="abstract" class="abstract topic">',
            output)

        # footnote refs looking a bit too superskripted
        # output = re.sub(
        #     '(?sm)<a class="footnote-reference" (.*?)><sup>(.*?)</sup></a>',
        #     r'<a class="footnote-reference" \1>\2</a>',
        #     output)

        # drop shadow wrappers for figures
        output = replace_drop_shadows(
            r'<div class="figure\1<div class="wrap1"><div class="wrap2"><div class="wrap3"><img\2/></div></div></div>\3</div>',
            output)

        # @/@ reinstate this? -- name="" no no
        # output = re.sub(r'<a name="table-of-contents"></a>', '', output)
        # output = re.sub(r'<a (.*?) name="(.*?)">', r'<a \1>', output)

        # get rid of <p>around floating images</p>
        # output = re.sub(
        #     '(?sm)<p><img (.*?) class="float-(.*?) /></p>',
        #     r'<img \1 class="float-\2 />',
        #     output)

        # niser <hr />
        # output = re.sub(
        #     '<hr />',
        #    r'<hr noshade="noshade" />',
        #    output)

        # drop cap them first letters
        # output = re.sub(
        #     '(?sm)<p>(.*?)</p>',
        #     render_drop_cap,
        #     output, count=1)

        # strip out comments
        output = replace_comments('', output)

        # strip out title headings
        output = replace_title_headings('', output)

    if with_props:
        if format == 'html':
            props.setdefault(u'title', visitor.title and visitor.title[0] or u'')
            props.setdefault(u'subtitle', visitor.subtitle and visitor.subtitle[0] or u'')
        return output, props

    return output

    # you kan do the above by using ``docutils.core`` pub = Publisher() ...
    # but it's a pretty ineffisient way of going about converting to HTML/LaTeX

    # anyways, speaking of pubs...

    # --------------------------------------------------------------------------
    #
    # A man goes into a pub, and the barmaid asks what he wants.
    #
    # "I want to bury my face in your cleavage and lick the sweat from between
    # your tits" he says.
    #
    # "You dirty git!" shouts the barmaid, "get out before I fetch my husband."
    #
    # The man apologises and promises not to repeat his gaffe.
    #
    # The barmaid accepts this and asks him again what he wants.
    #
    # "I want to pull your pants down, spread yoghurt between the cheeks of
    # your arse and lick it all off" he says.
    #
    # "You dirty filthy pervert. You're banned! Get out!" she storms.
    #
    # Again the man apologies and swears never ever to do it again.
    #
    # "One more chance" says the barmaid.
    #
    # "Now what do you want?" "I want to turn you upside down, fill your fanny
    # with Guinness, and then drink every last drop."
    #
    # The barmaid is furious at this personal intrusion, and runs upstairs to
    # fetch her husband, who's sitting quietly watching the telly.
    #
    # "What's up, Love?" he asks.
    #
    # "There's a man in the bar who wants to put his head between my tits and
    # lick the sweat off" she says.
    #
    # "I'll kill him. Where is he?" storms the husband.
    #
    # "Then he said he wanted to pour yoghurt down between my arse cheeks and
    # lick it off" she screams.
    #
    # "Right. He's dead!" says the husband, reaching for a baseball bat.
    #
    # "Then he said he wanted to turn me upside down, fill my fanny with
    # Guinness and then drink it all" she cries.
    #
    # The husband puts down his bat and returns to his armchair, and switches
    # the telly back on.
    #
    # "Aren't you going to do something about it?" she cries hysterically.
    #
    # "Look love -- I'm not messing with someone who can drink 12 pints of
    # Guinness..."
    #
    # --------------------------------------------------------------------------

