#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
interface.py - a GTK+ frontend for the Apoo processor
Copyright (C) 2006-2010 Ricardo Cruz <rpmcruz@alunos.dcc.fc.up.pt>

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License along
with this program; if not, write to the Free Software Foundation, Inc.,
51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
"""

import os, sys
import ConfigParser

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('Pango', '1.0')
gi.require_version('GObject', '2.0')
from gi.repository import Gtk, Gdk, Pango, GObject

from vpu import *
from constants import *

VERSION = "2.3.0"

# Definitions (non-configurable)
APOO_CONFIG_FILE = os.path.join (os.path.expanduser('~'), ".apoo")
DOCS_PATH = "/usr/share/doc/apoo/"
if not os.path.exists (DOCS_PATH):
    dirname = os.path.dirname (sys.argv[0])
    if len (dirname): DOCS_PATH = dirname + "/docs/"
    else: DOCS_PATH = "docs/"
DOC_APOO = "help_apoo"
DOC_TESTER = "help_tester"
DOC_ASSEMBLY = "help_assembly"
EXAMPLES_PATH="/usr/share/doc/apoo/examples/"
DATA_PATH=""

# Configurable (via arguments):
test_mode = False  # --tester

# Configurable (via the preferences dialog):
preferences = {
    "desktop_keys" : False,
    "emacs_keys" : True,
    "mirror_memory" : False,
    "mirror_memory_hor" : True,
    "mirror_memory_ver" : False,

    "registers_nb" : 8,
    "ram_size" : 1000,
    "max_steps" : 1000,
    "input_output" : 50001,
    "output_ascii" : 50000,
    "output_cr"    : 50010,
};
PREFERENCES = preferences.copy()  # keep the defaults as PREFERENCES
default_dir = None

# since we don't localize our strings, tell GTK to use English as well
import locale ; locale.setlocale (locale.LC_MESSAGES, 'C')

# Utilities
def digits_on (nb):  # returns the digits of a number (eg. 250 => 3)
    if nb < 10: return 1
    return digits_on (nb / 10) + 1
def is_blank (ch):  # helpers
    return ch == ' ' or ch == '\t' or ch == '\n' or ch == '\0'
def reverse_lookup (dict, value):
    for i in dict.keys():
        if dict[i] == value:
            return i
    return None

def show_error (text):
    windows = Gtk.window_list_toplevels()
    parent = None
    if len (windows) > 0:
        parent = windows[-1]
    dialog = Gtk.MessageDialog (parent, 0, Gtk.MESSAGE_ERROR,
        Gtk.ButtonsType.CLOSE, "Error")
    dialog.format_secondary_text (text)
    dialog.run()
    dialog.destroy()

def builder_from_file (filename):
    builder = Gtk.Builder()
    if builder.add_from_file (DATA_PATH + filename) == 0:
        show_error ("Couldn't load UI file: " + filename)
        return None
    return builder

# We need to explicitely specify font size, so let's get what
# was the font size (which would be the default)
def set_monospace_font (widget):
    font_desc = widget.get_pango_context().get_font_description()
    font_desc.set_family ("monospace")
    widget.modify_font (font_desc)

# By specifying a tone (from 0 to 255) and a style, it calculates a
# proper color.
def get_tone_color (style, tone):
    # we find the highest color component, and calculate the ratios accordingly
    # so, eg: (84, 151, 213) -> (0.39, 0.71, 1.00)
    syscolor = style.bg [Gtk.STATE_SELECTED]
    max_color = max (max (syscolor.red, syscolor.green), syscolor.blue)
    red_ratio   = (syscolor.red   * 1.0) / max_color
    green_ratio = (syscolor.green * 1.0) / max_color
    blue_ratio  = (syscolor.blue  * 1.0) / max_color

    red   = int (red_ratio   * tone)
    green = int (green_ratio * tone)
    blue  = int (blue_ratio  * tone)
    return Gdk.RGBA(red/255., green/255., blue/255.)

## Our own widgets

# Extends GtkTextBuffer to add some basic functionality:
# * undo/redo, * file reading/writting
class TextBufferExt (Gtk.TextBuffer):
    def __init__ (self):
        Gtk.TextBuffer.__init__(self)
        # actions stacks, so we can undo/redo
        self.undo_reset()
        self.ignore_event = False

    # public:
    def undo_reset (self):
        self.do_stack = []  # of type [ ('i', 30, "text"), ('d', 20, "other") ]
        self.do_stack_ptr = 0

    def can_undo (self):
        return self.do_stack_ptr > 0
    def can_redo (self):
        return self.do_stack_ptr < len (self.do_stack)

    def undo (self):
        if self.can_undo():
            self.do_stack_ptr -= 1
            action = self.do_stack [self.do_stack_ptr]
            self.do (action, True)
            if not self.can_undo():
                self.set_modified (False)

    def redo (self):
        if self.can_redo():
            action = self.do_stack [self.do_stack_ptr]
            self.do_stack_ptr += 1
            self.do (action, False)

    def read (self, filename):
        try:
            file = open (filename, 'r')
            self.set_text (file.read())
            file.close()
        except IOError: return False
        self.undo_reset()
        self.set_modified (False)
        return True

    def write (self, filename):
        try:
            file = open (filename, 'w')
            file.write (self.get_text (self.get_start_iter(), self.get_end_iter(), False))
            file.close()
        except IOError: return False
        self.set_modified (False)
        return True

    def get_insert_iter (self):
        return self.get_iter_at_mark (self.get_insert())

    # private:
    def do_insert_text (self, iter, text, length):
        if not self.ignore_event:
            action = ('i', iter.get_offset(), text)
            self.do_stack [self.do_stack_ptr:] = [action]
            self.do_stack_ptr += 1
        Gtk.TextBuffer.do_insert_text (self, iter, text, length)

    def do_delete_range (self, start_it, end_it):
        if not self.ignore_event:
            action = ('d', start_it.get_offset(), self.get_text (start_it, end_it, False))
            self.do_stack [self.do_stack_ptr:] = [action]
            self.do_stack_ptr += 1
        Gtk.TextBuffer.do_delete_range (self, start_it, end_it)

    def do (self, action, undo):
        iter = self.get_iter_at_offset (action[1])
        if (action[0] == 'd' and undo) or (action[0] == 'i' and not undo):
            self.ignore_event = True
            self.insert (iter, action[2])
            self.ignore_event = False
        else:
            end_iter = self.get_iter_at_offset (action[1] + len (action[2]))
            self.ignore_event = True
            self.delete (iter, end_iter)
            self.ignore_event = False

GObject.type_register (TextBufferExt)

# Extends GtkTextBuffer (actually our TextBufferExt) to add Editor-specific
# functionality
class EditorBuffer (TextBufferExt):
    def __init__ (self, editor):
        TextBufferExt.__init__(self)
        self.create_tag("comment", foreground="darkgrey", style=Pango.Style.OBLIQUE) 
        self.create_tag("assign",  foreground="darkred")  # eg: function:
        self.create_tag("instruction", weight=Pango.Weight.BOLD)  # eg: loadn
        self.create_tag("error", underline=Pango.Underline.ERROR)
        self.connect_after("notify::cursor-position", self.cursor_moved_cb)

        self.cursor_line = 0
        self.line_edited = False  # was current line edited?
        self.editor = editor

    # cuts the line into [(word, start_iter, end_iter), ...]
    class Split:
        def __init__ (self, word, start_it, end_it):
            self.word = word
            self.start_it = start_it
            self.end_it = end_it

    def split_line (self, line):
        iter = self.get_iter_at_line (line)
        if iter.is_end():
            return None
        splits = []
        while not iter.ends_line():
            while is_blank (iter.get_char()) and not iter.ends_line():
                iter.forward_char()
            if iter.ends_line(): break
            start_iter = iter.copy()
            while not is_blank (iter.get_char()) and not iter.ends_line():
                iter.forward_char()
            word = start_iter.get_text (iter).encode()
            splits += [EditorBuffer.Split (word, start_iter, iter.copy())]
        return splits

    def remove_line_tags (self, line):
        line_iter = self.get_iter_at_line (line)
        if line_iter.ends_line():
            return  # blank line -- you'd cross to next
        line_end_iter = line_iter.copy()
        line_end_iter.forward_to_line_end()
        self.remove_all_tags (line_iter, line_end_iter)

    def is_word_register (self, word):
        if word == None: return False
        if len (word) < 2: return False
        if word[0] != 'r' and word[0] != 'R': return False
        if len (word) == 2:
            if  word[1] == 's' or word[1] == 'S' or word[1] == 'f' or word[1] == 'F':
                return True
        for i in xrange (1, len (word)):
            if word[i] < '0' or word[i] > '9':
                return False
        return True

    # as-you-type highlighting. Iterates every line touched.
    def apply_highlight (self, start_line, end_line):
        line = start_line
        while line <= end_line:
            splits = self.split_line (line)
            if splits == None:
                break
            self.remove_line_tags (line)
            line += 1

            length = len (splits)
            if length == 0:
                continue

            comment = None
            for i in xrange (len (splits)):
                if splits[i].word[0] == '#':
                    comment = splits[i]
                    length = i
                    break

            address = None
            instr = None
            args = [None, None]
            args_nb = 0
            i = 0
            if splits[i].word[-1] == ':':
                address = splits[i]
                i += 1
            if length > i:
                instr = splits[i]
                i += 1
                args_nb = length - i
                if args_nb >= 1:
                    args[0] = splits[i]
                if args_nb >= 2:
                    args[1] = splits[i+1]

            if address != None:
                end_it = address.end_it.copy()
                end_it.backward_char()  # don't highlight the ':'
                self.apply_tag_by_name ("assign", address.start_it, end_it)
            match_instr = False
            if instr != None:
                for categories in inst:
                    for i in categories:
                        if instr.word == i:
                            match_instr = True
                            self.apply_tag_by_name ("instruction",
                                instr.start_it, instr.end_it)
            if comment != None:
                self.apply_tag_by_name ("comment", comment.start_it, splits[-1].end_it)

            if line-1 != self.get_insert_iter().get_line() and (address != None or instr != None) and self.editor.mode.mode == Editor.Mode.EDIT:
                error = not match_instr or args_nb > 2
                if not error:
                    # arguments semantics: ' ' - none, 'r' - register, 'n' - non-register
                    error_inst = ((' ',' '), ('n',' '), ('r',' '), ('r','r'), ('n','r'),
                                  ('r','n'))
                    for i in xrange (6):
                        for w in inst[i]:
                            if w == instr.word:
                                for j in xrange(2):
                                    if error_inst[i][j] == ' ':
                                        error = error or args[j] != None
                                    elif args[j] == None:
                                        error = True
                                    elif error_inst[i][j] == 'r':
                                        error = error or not self.is_word_register (args[j].word)
                                    elif error_inst[i][j] == 'n':
                                        error = error or self.is_word_register (args[j].word)

                if error:
                    start_it = splits[0].start_it
                    end_it = splits[length-1].end_it
                    self.apply_tag_by_name ("error", start_it, end_it)

    def cursor_moved_cb (self, buffer, pos_ptr):
        line = self.get_insert_iter().get_line()
        if line != self.cursor_line:
            if self.line_edited:
                self.apply_highlight (self.cursor_line, self.cursor_line)
                self.line_edited = False
            self.cursor_line = line

    def do_insert_text (self, iter, text, length):
        TextBufferExt.do_insert_text (self, iter, text, length)
        self.line_edited = True

        # as-you-type highlighting
        start = iter.copy()
        start.set_offset (iter.get_offset() - length)
        self.apply_highlight (start.get_line(), iter.get_line())

        # simple auto-identation; if the user typed return, apply the same
        # identation of the previous line
        if length == 1 and text == "\n":
            start_it = iter.copy()
            if start_it.backward_line():
                end_it = start_it.copy()
                while end_it.get_char() == ' ' or end_it.get_char() == '\t':
                    end_it.forward_char()

                if start_it.compare (end_it) != 0:  # there is identation
                    ident = self.get_text (start_it, end_it)    
                    self.insert (iter, ident)

    def do_delete_range (self, start_it, end_it):
        TextBufferExt.do_delete_range (self, start_it, end_it)
        self.apply_highlight (start_it.get_line(), end_it.get_line())

    # hooks for emacs-like region mark (ctrl+space)
    def cursor_moved (self, view, step_size, count, extend_selection):
        mark = self.get_mark ("emacs-mark")
        if mark:
            self.select_range (self.get_iter_at_mark (self.get_insert()),
                               self.get_iter_at_mark (mark))
    def do_changed (self):  # disable emacs' mark region
        Gtk.TextBuffer.do_changed (self)
        mark = self.get_mark ("emacs-mark")
        if mark: self.delete_mark (mark)

# The Editor widget, an extension over Gtk.TextView to support eg. line numbering
class Editor (Gtk.TextView):
    class Mode(object):
        EDIT = 0
        RUN  = 1
        def __init__ (self, editor):
            self.editor = editor
            self.line_color = None
            self.set_mode (None)

        def set_mode (self, vpu):
            if vpu == None:
                self.mode = self.EDIT
                self.alternative_numbering = None
                self.fixed_line = -1
                self.editor.breakpoints = []
            else:
                if self.mode == self.RUN:
                    self.editor.reload_breakpoints (vpu)
                self.mode = self.RUN
                self.alternative_numbering = {}
                for i in xrange (len (vpu.lines)):
                    self.alternative_numbering [vpu.lines[i]-1] = i

            # We don't want to set the editor insensitive to allow users
            # to do selections and that. So we mimic half of it.
            editable = self.mode == self.EDIT
            self.editor.set_editable (editable)
            self.editor.set_cursor_visible (editable)
            self.editor.set_name('editable' if editable else 'readonly')

        def set_current_line (self, line):
            if self.mode == self.EDIT:
                self.fixed_line = -1
            if line >= 0:
                buffer = self.editor.get_buffer()
                it = buffer.get_iter_at_line (line)
                buffer.place_cursor (it)
                # make line visible
                self.editor.scroll_to_iter (it, 0.10, False, 0.5, 0.5)
                self.fixed_line = line-1
            self.editor.queue_draw()  # update line highlight

        def set_current_line_color (self, color):
            if color == "white":
                color = None
            self.line_color = color
            self.editor.queue_draw()

        def get_current_line (self, window):
            if self.mode == self.EDIT:
                buffer = self.editor.get_buffer()
                iter = buffer.get_iter_at_mark (buffer.get_insert())
                curline = iter.get_line()

                fill_gc = self.editor.style.bg_gc [Gtk.STATE_NORMAL]
                stroke_gc = None
            else:
                curline = self.fixed_line

                color = get_tone_color (self.editor.style, 255)
                if self.line_color != None:
                    clr = self.line_color
                    color = Gtk.gdk.color_parse (clr)
                fill_gc = window.new_gc()
                fill_gc.set_rgb_fg_color (color)

                color = get_tone_color (self.editor.style, 150)
                if self.line_color != None:
                    clr = self.line_color + "4"
                    color = Gtk.gdk.color_parse (clr)
                stroke_gc = window.new_gc()
                stroke_gc.set_rgb_fg_color (color)
            return (curline, fill_gc, stroke_gc)

        def get_line_number (self, line):
            if self.alternative_numbering:
                try:    line = self.alternative_numbering [line]
                except: line = -1
            else:
                line = line+1
            return line

    def __init__ (self, parent):
        Gtk.TextView.__init__ (self)
        buffer = EditorBuffer(self)
        self.set_buffer(buffer)
        self.main_parent = parent

        self.set_tabs (Pango.TabArray (4, False))
        set_monospace_font (self)
        self.set_wrap_mode (Gtk.WrapMode.WORD_CHAR)
        self.set_left_margin (1)

        '''
        font_desc = self.get_pango_context().get_font_description()
        metrics = self.get_pango_context().get_metrics (font_desc, None)
        self.digit_width = PANGO_PIXELS(metrics.get_approximate_digit_width())
        self.digit_height = PANGO_PIXELS(metrics.get_ascent()) + PANGO_PIXELS(metrics.get_descent())
        '''
        self.digit_width = 15
        self.digit_height = 10

        self.margin_digits = 99  # to force a margin calculation
        self.text_changed(buffer)  # sets the numbering margin

        self.do_stack = [] # of type [ ('i', 30, "text"), ('d', 20,"other") ]
        # for re/undo
        self.do_stack_ptr = 0

        # printing setup
        self.settings = None

        # editor mode: edit, run, or error
        self.mode = Editor.Mode(self)

        buffer.connect ("changed", self.text_changed)
        self.connect_after ("move-cursor", buffer.cursor_moved)  # for the emacs mark

    def get_text (self):
        buffer = self.get_buffer()
        return buffer.get_text (buffer.get_start_iter(), buffer.get_end_iter(),
               False)

    def do_expose_event (self, event):  # draw command
        curline, fill_gc, stroke_gc = self.mode.get_current_line (event.window)

        # left window -- draw line numbering
        window = self.get_window (Gtk.TEXT_WINDOW_LEFT)
        if event.window == window:
            visible_text = self.get_visible_rect()
            iter = self.get_iter_at_location (visible_text.x, visible_text.y)

            layout = Pango.Layout (self.get_pango_context())
            last_loop = False
            while True:  # a do ... while would be nicer :/
                rect = self.get_iter_location (iter)
                x, y = self.buffer_to_window_coords (Gtk.TEXT_WINDOW_LEFT, rect.x, rect.y)

                if y > event.area.y + event.area.height: break
                if y + self.digit_height > event.area.y:
                    line = self.mode.get_line_number (iter.get_line())

                    # draw a half arc at the numbering window to finish current line
                    # rectangle nicely.
                    if iter.get_line() == curline and stroke_gc != None:
                        w = self.get_border_window_size (Gtk.TEXT_WINDOW_LEFT)
                        h = rect.height
                        window.draw_arc (fill_gc, True, 0, y, w, h, 90*64, 180*64)
                        window.draw_arc (stroke_gc, False, 0, y, w, h-1, 90*64, 180*64)

                        window.draw_rectangle (fill_gc, True, w/2, y+1, w/2, h-1)
                        window.draw_line (stroke_gc, w/2, y, w, y)
                        window.draw_line (stroke_gc, w/2, y+h-1, w, y+h-1)

                    # draw a circle for break points
                    if self.mode.mode == Editor.Mode.RUN:
                        if iter.get_line() in self.breakpoints:
                            color = Gtk.gdk.Color (237 << 8, 146 << 8, 146 << 8, 0)
                            gc = event.window.new_gc()
                            gc.set_rgb_fg_color (color)
                            color = Gtk.gdk.Color (180 << 8, 110 << 8, 110 << 8, 0)
                            out_gc = event.window.new_gc()
                            out_gc.set_rgb_fg_color (color)

                            w = self.get_border_window_size (Gtk.TEXT_WINDOW_LEFT)
                            h = rect.height
                            window.draw_arc (gc, True, 0, y, w, h, 0, 360*64)
                            window.draw_arc (out_gc, False, 0, y, w-1, h-1, 0, 360*64)

                    if line >= 0:
                        text = str (line).rjust (self.margin_digits, " ")  # align at right

                        if iter.get_line() == curline:
                            text = "<b>" + text + "</b>"
                        if self.mode.mode != Editor.Mode.EDIT:
                            text = "<span foreground=\"blue\">" + text + "</span>"

                        layout.set_markup (text)
                        self.style.paint_layout (window, Gtk.STATE_NORMAL, False, event.area,
                                                 self, "", 2, y, layout)
                if last_loop:
                    break
                if not iter.forward_line():
                    last_loop = True

        # text window -- highlight current line
        window = self.get_window (Gtk.TEXT_WINDOW_TEXT)
        if event.window == window:
            # do the current line highlighting now
            iter = self.get_buffer().get_iter_at_line (curline)
            y, h = self.get_line_yrange (iter)
            x, y = self.buffer_to_window_coords (Gtk.TEXT_WINDOW_TEXT, 0, y)
            w = self.allocation.width

            window.draw_rectangle (fill_gc, True, x, y, w, h)
            if stroke_gc != None:
                window.draw_line (stroke_gc, x, y, w, y)
                window.draw_line (stroke_gc, x, y + h - 1, w, y + h - 1)

        return Gtk.TextView.do_expose_event (self, event)

    # button pressed on numbering pane -- move cursor to that line
    # for two clicks, set break point
    # parent is a hook to be able to access Interface
    def do_button_press_event (self, event):
        Gtk.TextView.do_button_press_event (self, event)
        '''
        parent = self.main_parent
        if event.window == self.get_window (Gtk.TextWindowType.LEFT):
            x, y = self.window_to_buffer_coords (Gtk.TextWindowType.LEFT,
                                                 int (event.x), int (event.y))
            it = self.get_iter_at_location (x, y)
            self.get_buffer().place_cursor (it)

            if event.type == Gdk.2BUTTON_PRESS and self.mode.mode == Editor.Mode.RUN:
                line = it.get_line()
                vpu = parent.vpu.vpu

                # see if there is already one -- if so, remove it
                if line in self.breakpoints:  # remove it
                    try:
                        i = vpu.lines.index (line+1)
                    except ValueError:
                        parent.message.write ("%s %s" % ("Cannot clear a break point in line",
                                              line+1), "white")
                    else:
                        try:
                            vpu.clearbreak (i)
                        except:
                            parent.message.write ("Error: %s, %s" % (sys.exc_type,
                                                  sys.exc_value), "red")
                        else:
                            self.breakpoints.remove (line)
                else:  # add break point
                    try:
                        i = vpu.lines.index (line+1)
                    except ValueError:
                        parent.message.write ("%s %s" % ("Cannot set a break point in line",
                                              line+1), "white")
                    else:
                        try:
                            vpu.setbreak (i)
                        except:
                            parent.message.write ("Error: %s, %s" % (sys.exc_type, sys.exc_value),
                                                  "red")
                        else:
                            self.breakpoints.append (line)
        '''

    def reload_breakpoints (self, vpu):
        for i in self.breakpoints:
            pt = vpu.lines.index (i+1)
            vpu.setbreak (pt)

    # we use this so we know when lines are inserted or removed and change the
    # line numbering border accordingly
    def text_changed (self, buffer):
        digits = max (digits_on (buffer.get_line_count()), 2)
        if digits != self.margin_digits:
            self.margin_digits = digits
            margin = (self.digit_width * digits) + 4
            self.set_border_window_size (Gtk.TextWindowType.LEFT, margin)

    # Printing support
    def print_text (self, parent_window, title):
        print_data = self.PrintData()
        print_data.header_title = title
        print_op = Gtk.PrintOperation()

        if self.settings != None:
            print_op.set_print_settings (self.settings)
  
        print_op.connect ("begin-print", self.print_begin_cb, print_data)
        print_op.connect ("draw-page", self.print_page_cb, print_data)

        try:
            res = print_op.run (Gtk.PRINT_OPERATION_ACTION_PRINT_DIALOG, parent_window)
        except GObject.GError as ex:
            show_error ("While printing:\n%s" % str(ex))
        else:
            if res == Gtk.PRINT_OPERATION_RESULT_APPLY:
                self.settings = print_op.get_print_settings()

    class PrintData:
        layout = None
        page_breaks = None
        header_title = None
        header_height = 0
        header_layout = None

    def print_begin_cb (self, operation, context, print_data):
        width = context.get_width()
        height = context.get_height()
        print_data.layout = context.create_pango_layout()
        print_data.layout.set_font_description (Pango.FontDescription ("Monospace 12"))
        print_data.layout.set_width (int (width * Pango.SCALE))
        # create a layout based on the text with applied tags for printing
        it = self.get_buffer().get_start_iter()
        text = ""
        tags = self.get_buffer().get_tag_table()
        comment_tag = tags.lookup ("comment")
        assign_tag = tags.lookup ("assign")
        instruction_tag = tags.lookup  ("instruction")
        while not it.is_end():
            if it.ends_tag (None):
                text += "</span>"
            if it.starts_line():
                text += "<span weight='normal' style='normal' foreground='black'>"
                text += str (it.get_line()+1).rjust (self.margin_digits, " ")
                text += "</span>  "
            if it.begins_tag (comment_tag):
                text += "<span foreground='darkgrey' style='oblique'>"
            if it.begins_tag (assign_tag):
                text += "<span foreground='darkred'>"
            if it.begins_tag (instruction_tag):
                text += "<span weight='bold'>"
            text += it.get_char()
            it.forward_char()
        print_data.layout.set_markup (text)

        print_data.header_layout = context.create_pango_layout()
        print_data.header_layout.set_font_description (Pango.FontDescription ("Sans 12"))
        print_data.header_layout.set_width (int (width * Pango.SCALE))
        print_data.header_layout.set_text ("title")
        header_height = print_data.header_layout.get_extents()[1][3] / 1024.0
        print_data.header_height = header_height + 10

        num_lines = print_data.layout.get_line_count()
        page_breaks = []
        page_height = 0

        for line in xrange (num_lines):
            layout_line = print_data.layout.get_line (line)
            ink_rect, logical_rect = layout_line.get_extents()
            lx, ly, lwidth, lheight = logical_rect
            line_height = lheight / 1024.0
            if page_height + line_height + header_height > height:
                page_breaks.append (line)
                page_height = 0
            page_height += line_height

        operation.set_n_pages (len (page_breaks) + 1)
        print_data.page_breaks = page_breaks

    def print_page_cb (self, operation, context, page_nr, print_data):
        assert isinstance (print_data.page_breaks, list)
        if page_nr == 0:
            start = 0
        else:
            start = print_data.page_breaks [page_nr - 1]
        try:
            end = print_data.page_breaks [page_nr]
        except IndexError:
            end = print_data.layout.get_line_count()

        cr = context.get_cairo_context()
        cr.set_source_rgb(0, 0, 0)

        # print page header
        header_height = print_data.header_height
        header_layout = print_data.header_layout
        cr.move_to (0, header_height-4)
        cr.line_to (context.get_width(), header_height-4)
        cr.stroke()
        if print_data.header_title != None:
            cr.move_to (6, 3)
            header_layout.set_text (print_data.header_title)
            cr.show_layout (header_layout)
        header_layout.set_text ("Page %s of %s" % (page_nr+1,
                                len (print_data.page_breaks)+1))
        x = header_layout.get_extents()[1][2] / 1024.0
        x = context.get_width() - x
        cr.move_to (x-6, 3)
        cr.show_layout (header_layout)

        # print body -- the text
        cr.set_source_rgb (0, 0, 0)
        i = 0
        start_pos = 0
        iter = print_data.layout.get_iter()
        while True:
            if i >= start:
                line = iter.get_line()
                _, logical_rect = iter.get_line_extents()
                lx, ly, lwidth, lheight = logical_rect
                baseline = iter.get_baseline()
                if i == start:
                    start_pos = ly / 1024.0;
                cr.move_to (lx / 1024.0, baseline / 1024.0 - start_pos + header_height)
                cr.show_layout_line (line)
            i += 1
            if not (i < end and iter.next_line()):
                break

GObject.type_register (Editor)

# The setup dialog
def read_config():
    config = ConfigParser.ConfigParser()
    config.read (APOO_CONFIG_FILE)

    for i in preferences.keys():
        if config.has_option ("preferences", i):
            preferences[i] = int (config.get ("preferences", i))

    global default_dir
    if config.has_option ("session", "default-dir"):
        default_dir = config.get ("session", "default-dir")

def write_config():
    config = ConfigParser.ConfigParser()

    config.add_section ("preferences")
    for i in preferences.keys():
        config.set ("preferences", i, str (preferences[i]))

    if default_dir != None:
        config.add_section ("session")
        config.set ("session", "default-dir", default_dir)

    file = open (APOO_CONFIG_FILE, 'w')
    config.write (file)
    file.close()

# set as Gtk.Entry "changed" callback to accept only integers
def numeric_entry_changed_cb (entry):
    text = entry.get_text()
    if text == "" or text == "-": return
    try: value = int (text)
    except ValueError:
        entry.set_text ("")
        entry.error_bell()
        entry.modify_base (Gtk.STATE_NORMAL, Gtk.gdk.Color (0xffff, 0, 0))
        def _restore (entry):
            entry.modify_base (Gtk.STATE_NORMAL, None)
            return False
        GObject.timeout_add (50, _restore, entry)

def entry_get_text_as_int (entry):
    text = entry.get_text()
    try: val = int (text)
    except: return 0
    return val

class PreferencesDialog:
    def __init__ (self):
        builder = builder_from_file ("ui/preferences.ui")
        if builder == None:
            self.window = None
            return
        self.preferences_widgets = {}
        for i in preferences.keys():
            widget = builder.get_object (i)
            self.preferences_widgets[i] = widget
            value = preferences[i]
        self.mirror_box = builder.get_object ("mirror-box")
        self.load()
        builder.connect_signals (self)

        self.window = builder.get_object ("dialog")
        windows = Gtk.window_list_toplevels()
        self.window.set_transient_for (windows[0])

    def show (self):
        if self.window != None:
            self.window.present()

    def load (self):  # set current preferences         
        for i in preferences.keys():
            widget = self.preferences_widgets[i]
            value = preferences[i]
            if isinstance (widget, Gtk.ToggleButton):
                widget.set_active (bool (value))
            else:
                widget.set_text (str (value))
        self.sync()

    def write (self):
        for i in preferences.keys():
            widget = self.preferences_widgets[i]
            value = preferences[i]
            if isinstance (widget, Gtk.ToggleButton):
                preferences[i] = int (widget.get_active())
            else:
                preferences[i] = entry_get_text_as_int (widget)
        self.sync()
        for i in windows:
            i.sync_preferences()

    def sync (self):
        mirror_check = self.preferences_widgets["mirror_memory"]
        self.mirror_box.set_sensitive (mirror_check.get_active())

    def on_dialog_response (self, dialog, response):
        if response == 1:  # revert
            self.load()
        else:
            self.window.hide()

    def on_dialog_delete_event (self, dialog, event):
        dialog.hide()
        return True

    def on_value_changed (self, entry):
        numeric_entry_changed_cb (entry)
        self.write()

    def on_value_toggled (self, button):
        if button.get_active():
            self.write()

    def on_value_always_toggled (self, button):
        self.write()

preferences_dialog = None
def show_preferences():
    global preferences_dialog
    if preferences_dialog == None:
        preferences_dialog = PreferencesDialog()
    preferences_dialog.show()

## The table stack pointer renderer
class CellRendererStackPointer (Gtk.CellRenderer):
    ARROW_WIDTH = ARROW_HEIGHT = 8
    # pointer enum
    POINTER_NONE   = 0
    POINTER_ARROW  = 1
    POINTER_MIDDLE = 2

    __gproperties__ = {
        'pointer': (GObject.TYPE_INT, 'pointer property',
                     'Pointer relatively to the data being pointed to.',
                     0, 4, POINTER_NONE, GObject.PARAM_READWRITE),
    }

    def __init__(self):
        Gtk.CellRenderer.__init__(self)
        self.pointer = self.POINTER_NONE

    def do_get_property(self, pspec):
        if pspec.name == "pointer":
            return self.pointer
        else:
            raise AttributeError, 'unknown property %s' % pspec.name

    def do_set_property (self, pspec, value):
        if pspec.name == "pointer":
            self.pointer = value
            self.notify ("pointer")
        else:
            raise AttributeError, 'unknown property %s' % pspec.name

    def do_render (self, window, widget, bg_area, cell_area, expose_area, flags):
        print 'render cell arrow !!'
        if self.pointer == self.POINTER_NONE:
            return

        bg_gc = window.new_gc()
        bg_gc.set_rgb_fg_color (get_tone_color (widget.style, 255))
        fg_gc = window.new_gc()
        fg_gc.set_rgb_fg_color (get_tone_color (widget.style, 140))
        fg_gc.set_line_attributes (2, Gtk.gdk.LINE_SOLID, Gtk.gdk.CAP_ROUND,
                                   Gtk.gdk.JOIN_MITER)

        # pointer drawing
        x = cell_area.x
        y = bg_area.y
        w = cell_area.width  # self.ARROW_WIDTH
        h = bg_area.height
        if self.pointer == self.POINTER_MIDDLE:
            window.draw_line (fg_gc, x + w/2, y, x + w/2, y+h)

        else:
            x = cell_area.x
            w = self.ARROW_WIDTH
            y = cell_area.y + cell_area.height/2
            h = self.ARROW_HEIGHT

            points = [ (x, y), (x + w, y - h/2), (x + w, y + h/2) ]
            window.draw_polygon (bg_gc, True, points)
            window.draw_polygon (fg_gc, False, points)

    def do_get_size (self, widget, cell_area):
        return 0, 0, self.ARROW_WIDTH, self.ARROW_HEIGHT

## VPU Model

class VpuModel:
    class ListModel (GObject.Object, Gtk.TreeModel):
        def __init__ (self, list):
            GObject.Object.__init__(self)
            self.list = list

        def do_get_flags (self):
            return Gtk.TreeModelFlags.ITERS_PERSIST | Gtk.TreeModelFlags.LIST_ONLY

        def do_get_iter (self, path):
            index = path[0]
            if index < len (self.list):
                iter_ = Gtk.TreeIter()
                iter_.user_data = index
                return (True, iter_)
            return (False, None)

        def do_get_path (self, iter_):
            if iter_.user_data is not None:
                return Gtk.TreePath((iter_.user_data,))
            return None

        def do_iter_next (self, iter_):
            if iter_.user_data+1 < len (self.list):
                iter_.user_data += 1
                return (True, iter_)
            return (False, None)

        def do_iter_has_child (self, iter):
            return False

        def do_iter_parent(self, child):
            return None

        def do_iter_n_children (self, iter):
            if iter == None:
                len (self.list)
            return 0

        def do_iter_nth_child (self, parent, n):
            if n < len (self.list):
                iter_ = Gtk.TreeIter()
                iter_.user_data = n
                return (True, iter_)
            return (False, None)

        def do_iter_children (self, parent):
            return self.on_iter_nth_child (parent, 0)

        def do_get_value(self, iter_, column):
            return self.get_value(iter_.user_data, column)


    class RamModel (ListModel):
        def __init__ (self, vpu):
            VpuModel.ListModel.__init__ (self, vpu.RAM)
            self.vpu = vpu

        INDEX_COL = 0
        LABEL_COL = 1
        VALUE_COL = 2
        INDEX_COLOR_COL = 3
        LABEL_COLOR_COL = 4
        VALUE_COLOR_COL = 5
        BACKGROUND_COLOR_COL = 6
        REGS_POINTER_COL = 7
        REGS_POINTER_TEXT_COL = 8

        def do_get_n_columns (self): return 9

        def do_get_column_type (self, col):
            if col == self.INDEX_COL: return str
            elif col == self.LABEL_COL: return str
            elif col == self.VALUE_COL: return str
            elif col == self.INDEX_COLOR_COL: return str
            elif col == self.LABEL_COLOR_COL: return str
            elif col == self.VALUE_COLOR_COL: return str
            elif col == self.BACKGROUND_COLOR_COL: return Gdk.RGBA
            elif col == self.REGS_POINTER_COL: return int
            elif col == self.REGS_POINTER_TEXT_COL: return str

        def get_value (self, index, col):
            if col == self.INDEX_COL:
                return str (index)
            elif col == self.LABEL_COL:
                label = reverse_lookup (self.vpu.labelm, index)
                if label == None:
                    label = ""
                return label
            elif col == self.VALUE_COL:
                return str (self.list [index])
            elif col == self.INDEX_COLOR_COL:
                if index in self.vpu.mem_changed:
                    return "red"
                return "blue"
            elif col == self.LABEL_COLOR_COL:
                if index in self.vpu.mem_changed:
                    return "red"
                return "darkred"
            elif col == self.VALUE_COLOR_COL:
                if index in self.vpu.mem_changed:
                    return "red"
                return "black"
            elif col == self.BACKGROUND_COLOR_COL:
                rf = self.vpu.reg [-2]
                rs = self.vpu.reg [-1]
                if index < rf or index > rs:
                    if index % 2 == 1:
                        return Gdk.RGBA(0.95, 0.67, 0.67)
                    return Gdk.RGBA(1, 0.7, 0.7)
                if index % 2 == 1:
                    return Gdk.RGBA(0.93, 0.93, 0.93)
                return Gdk.RGBA(1, 1, 1)
            elif col == self.REGS_POINTER_COL:
                if len (self.vpu.reg) >= 2:
                    rf = self.vpu.reg [-2]
                    rs = self.vpu.reg [-1]
                    if index == rf or index == rs:
                        return CellRendererStackPointer.POINTER_ARROW
                    if index > rf and index < rs:
                        return CellRendererStackPointer.POINTER_MIDDLE
                return CellRendererStackPointer.POINTER_NONE
            elif col == self.REGS_POINTER_TEXT_COL:
                if len (self.vpu.reg) >= 2:
                    rf = self.vpu.reg [-2]
                    rs = self.vpu.reg [-1]
                    if index == rf:
                        if index == rs:
                            return "r"
                        return "rf"
                    if index == rs:
                        return "rs"
                return ""

        def sync (self):
            changed = {}
            for i in self.vpu.mem_changed:
                changed[i] = True
            for i in self.vpu.last_mem_changed:
                changed[i] = True
            rf = self.vpu.reg [-2]
            rs = self.vpu.reg [-1]
            last_rf = self.vpu.last_reg [-2]
            last_rs = self.vpu.last_reg [-1]
            if last_rs != rs or last_rf != rf:
                for i in xrange (min (last_rf, last_rs), max (last_rf, last_rs)+1):
                    changed[i] = True
                for i in xrange (min (rf, rs), max (rf, rs)+1):
                    changed[i] = True
            for i in changed:
                if i >= 0:
                    path = (i,)
                    iter = self.get_iter (path)
                    self.row_changed (path, iter)

    class RegModel (ListModel):
        def __init__ (self, vpu):
            VpuModel.ListModel.__init__ (self, vpu.reg)
            self.vpu = vpu

        INDEX_COL = 0
        VALUE_COL = 1
        COLOR_COL = 2

        def do_get_n_columns (self): return 3

        def do_get_column_type (self, col):
            if col == self.INDEX_COL:
                return str
            elif col == self.VALUE_COL:
                return str
            elif col == self.COLOR_COL:
                return str

        def get_value (self, index, col):
            if col == self.INDEX_COL:
                s = "R%d" % index
                if self.vpu.nreg >= 2:
                    if index == self.vpu.nreg-2:
                        s += " / RF"
                    elif index == self.vpu.nreg-1:
                        s += " / RS"
                return s
            elif col == self.VALUE_COL:
                return str (self.list [index])
            elif col == self.COLOR_COL:
                if index in self.vpu.reg_changed:
                    return "red"
                return "black"

        def sync (self):
            changed = {}
            for i in self.vpu.reg_changed:
                changed[i] = True
            for i in self.vpu.last_reg_changed:
                changed[i] = True
            for i in changed:
                path = Gtk.TreePath.new_from_indices([i])
                iter = self.get_iter (path)
                self.row_changed (path, iter)

    class Listener:
        def set_ram_model (self, model): pass
        def set_reg_model (self, model): pass
        def set_ram_scroll (self, path): pass
        def set_reg_scroll (self, path): pass
        def set_output_buffer (self, buffer): pass
        def set_program_counter (self, value): pass
        def set_timer_counter (self, value): pass
        def set_message (self, message, status, color): pass
        def get_program_code (self): pass

    def __init__ (self, listener):
        self.listener = listener
        self.ram_model = None
        self.reg_model = None

    def load (self):
        registers_nb = preferences["registers_nb"]
        input_output = preferences["input_output"]
        output_ascii = preferences["output_ascii"]
        output_cr = preferences["output_cr"]
        ram_size = preferences["ram_size"]
        self.vpu = Vpu (registers_nb,
                        { output_ascii:("val = 0", "self.Inter.output_inst (val, True)"),
                          input_output:("val = self.Inter.input_inst()",
                                        "self.Inter.output_inst (val)"),
                          output_cr:("val = 0", "self.Inter.output_inst()") }, self,
                        ram_size)
        self.vpu.last_reg = self.vpu.reg
        self.vpu.mem_changed = []
        self.vpu.reg_changed = []
        self.vpu.last_mem_changed = []
        self.vpu.last_reg_changed = []

        program = self.listener.get_program_code()
        try:
            self.vpu.load (program)
        except vpuLoadError,error:
            message = "Parsing Error (Ln %d): %s" % (error.line, error.message)
            self.listener.set_message (message, "parsing error", "red", error.line)
            return False
        except:
            message = "Parsing Error: %s, %s" % (sys.exc_type, sys.exc_value)
            self.listener.set_message (message, "parsing error", "red")
            return False

        self.listener.set_message ("Program Loaded", "loaded", "white")
        self.ram_model = VpuModel.RamModel (self.vpu)
        self.reg_model = VpuModel.RegModel (self.vpu)
        self.listener.set_ram_model (self.ram_model)
        self.listener.set_reg_model (self.reg_model)
        self.output_buffer = Gtk.TextBuffer()
        self.listener.set_output_buffer (self.output_buffer)
        self.visible_changes = False

        self.sync()
        return True

    def clear (self):
        self.ram_model = None
        self.reg_model = None
        self.output_buffer = None
        self.listener.set_ram_model (None)
        self.listener.set_reg_model (None)
        self.listener.set_output_buffer (None)
        self.listener.set_program_counter (0)
        self.listener.set_timer_counter (0)
        self.vpu = None

    def show_changes (self, visible):
        self.listener.set_message ("Running", "running", "white")
        self.vpu.last_mem_changed = self.vpu.mem_changed[:]
        self.vpu.last_reg_changed = self.vpu.reg_changed[:]
        self.vpu.last_reg = self.vpu.reg[:]
        self.vpu.mem_changed = []
        self.visible_changes = visible

    def sync (self):
        # vpu.mem_changed set while stepping; similar procedure for registers
        self.vpu.reg_changed = []
        for i in xrange (self.vpu.nreg):
            if self.vpu.reg[i] != self.vpu.last_reg[i]:
                self.vpu.reg_changed.append (i)

        self.listener.set_program_counter (self.vpu.PC)
        self.listener.set_timer_counter (self.vpu.time)
        self.ram_model.sync()
        self.reg_model.sync()

        if self.visible_changes:
            if len (self.vpu.mem_changed) > 0:
                self.listener.set_ram_scroll ((self.vpu.mem_changed[0],))
            if len (self.vpu.reg_changed) > 0:
                self.listener.set_reg_scroll ((self.vpu.reg_changed[0],))
        else:
            self.vpu.mem_changed = []
            self.vpu.reg_changed = []

    def _step (self, cur_step):
        try:
            mem_changed = self.vpu.step()
            if mem_changed != (None, None) and not mem_changed[0] in self.vpu.mem_changed:
                self.vpu.mem_changed.append (mem_changed[0])
            if cur_step > preferences["max_steps"]:
                raise TooManySteps (cur_step)
        except OutOfMemory, error:
            message = "%s: memory address %s not reserved" % (error.message, error.add)
            self.set_message (message, "end of program", error.colour)
        except vpuError, error:
            self.listener.set_message (error.message, "end of program", error.colour)
        except:
            message = "Error: %s, %s" % (sys.exc_type, sys.exc_value)
            self.listener.set_message (message, "end of program error", "red")
        else:
            return True
        return False

    def step (self, nb):
        self.show_changes (True)
        i = 0
        while self._step (0):
            i += 1
            if i >= nb:
                self.listener.set_message ("Next Step", "running", "white")
                break
        self.sync()

    def cont (self):
        self.show_changes (True)
        i = 0
        while self._step (i):
            if self._is_on_breakpoint():
                self.listener.set_message ("Continue Program", "at break point", "white")
                break
            i += 1
        self.sync()

    def run (self):
        self.show_changes (False)
        i = 0
        while self._step (i):
            i += 1
        self.sync()

    def _is_on_breakpoint (self):
        try:
            line = self.vpu.lines [self.vpu.PC]
            try:
                i = self.vpu.lines.index (line)
            except ValueError:
                return False
            try:
                b = self.vpu.BreakP.index (i)
            except ValueError:
                return False
            return True
        except IndexError:
            return False

    # graphical-dependent instructions
    def output_inst (self, value = '\n', convert_ascii = False):
        if convert_ascii:
            value = ("%c" % value).decode()
        buffer = self.output_buffer
        buffer.insert (buffer.get_end_iter(), "%s" % value)

    def input_inst (self):
        dialog = Gtk.Dialog.new_with_buttons ("Insert Input",
            self.listener.get_toplevel(),
                             Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
                             (Gtk.STOCK_OK, Gtk.ResponseType.ACCEPT))
        dialog.set_has_separator (False)
        dialog.set_default_response (Gtk.ResponseType.ACCEPT)

        label = Gtk.Label ("Input:")
        entry = Gtk.Entry()
        entry.connect ("changed", numeric_entry_changed_cb)
        entry.set_activates_default (True)

        box = Gtk.HBox (False, 6)
        box.set_border_width (6)
        box.pack_start (label, False, True, 0)
        box.pack_start (entry, True, True, 0)
        box.show_all()
        dialog.vbox.pack_start (box, True, True, 0)

        while dialog.run() != Gtk.ResponseType.ACCEPT:
            pass  # force user to accept

        value = entry_get_text_as_int (entry)
        dialog.destroy()
        return value

## The view

class Interface (Gtk.EventBox, VpuModel.Listener):
    def __init__ (self, filename):
        Gtk.EventBox.__init__ (self)
        self.vpu = VpuModel (self)
        self.main_parent = None

        builder = builder_from_file ("ui/page.ui")
        if builder == None: return
        self.editor = Editor (self)
        self.editor.show()
        scroll = builder.get_object ("editor_scroll")
        scroll.add (self.editor)
        self.editor.get_buffer().connect ("modified-changed",
            self.buffer_modified_cb)

        self.load_button = builder.get_object ("load_button")
        self.run_button = builder.get_object ("run_button")
        self.step_button = builder.get_object ("step_button")
        self.continue_button = builder.get_object ("continue_button")
        self.clear_button = builder.get_object ("clear_button")

        self.step_value = 1
        self.step_popup = Gtk.Menu()
        for i in xrange (1,21):
            item = Gtk.MenuItem (str (i))
            item.show()
            item.connect ("activate", self.on_step_popup_activate, i)
            self.step_popup.append (item)
        self.step_popup.attach_to_widget (self.step_button, None)

        self.editor_status = builder.get_object ("editor_label")
        self.editor.get_buffer().connect ("notify::cursor-position", self.cursor_moved_cb)
        self.vpu_status = builder.get_object ("vpu_label")

        edit_button = builder.get_object ("edit_button")
        if test_mode:
            edit_button.hide()

        self.counter = builder.get_object ("counter_entry")
        self.counter.set_name('counter_entry')
        self.timer = builder.get_object ("timer_entry")

        self.output = builder.get_object ("output_view")
        set_monospace_font (self.output)
        self.registers = builder.get_object ("registers_view")
        self.registers.get_selection().set_mode(Gtk.SelectionMode.NONE)
        self.memory = []
        for i in [1,2]:
            widget = builder.get_object ("memory_view" + str (i))
            self.memory.append (widget)
            widget.get_selection().set_mode (Gtk.SelectionMode.NONE)
        self.memory_label_column2 = builder.get_object ("memory_label_column2")
        self.memory_ptr_columns = []
        for i in [1,2]:
            column = builder.get_object ("memory_ptr_column" + str (i))
            self.memory_ptr_columns.append (column)

            view = self.memory[i-1]
            cell = CellRendererStackPointer()
            _, _, w1, _ = cell.do_get_size (view, None)
            column.pack_start (cell, False)
            column.set_attributes (cell,
                pointer = VpuModel.RamModel.REGS_POINTER_COL,
                cell_background_rgba=VpuModel.RamModel.BACKGROUND_COLOR_COL)
            cell = Gtk.CellRendererText()
            column.pack_start (cell, True)
            column.set_attributes (cell,
                text = VpuModel.RamModel.REGS_POINTER_TEXT_COL,
                cell_background_rgba=VpuModel.RamModel.BACKGROUND_COLOR_COL)

            layout = Pango.Layout (widget.get_pango_context())
            layout.set_text ("rs", -1)
            w2, _ = layout.get_pixel_size()
            column.set_fixed_width (w1 + w2 + 8)

        builder.get_object ("memory_label_column2")
        self.message = builder.get_object ("info_label")

        top = builder.get_object ("top")
        top.reparent (self)
        self.set_border_width (6)
        self.show()
        self.sync_preferences()
        builder.connect_signals (self)

        self.file_read (filename)
        self.vpu.clear()

    def sync_preferences (self):
        view2 = self.memory[1].get_parent()
        self.memory_ptr_columns[0].set_visible (True)
        if preferences["mirror_memory"]:
            view2.show()
            paned = view2.get_parent()
            if preferences["mirror_memory_hor"]:
                paned.set_orientation (Gtk.ORIENTATION_HORIZONTAL)
                self.memory_label_column2.set_visible (False)
                self.memory_ptr_columns[0].set_visible (False)
                self.memory[1].set_headers_visible (True)
            else:
                paned.set_orientation (Gtk.ORIENTATION_VERTICAL)
                self.memory_label_column2.set_visible (True)
                self.memory[1].set_headers_visible (False)
        else:
            view2.hide()

    def on_editor_scroll_realize (self, scroll):
        scroll.get_child().grab_focus()

    def create_informative (self, title):
        entry = Gtk.Entry()
        entry.set_editable (False)  # let's make people see the entry is un-editable...
        entry.modify_base (Gtk.STATE_NORMAL, entry.style.base [Gtk.STATE_INSENSITIVE]);
        entry.set_size_request (40, -1)

        label = Gtk.Label ("<span foreground=\"red\"><b>" + title + ":</b></span>")
        label.set_use_markup (True)
        label.set_use_underline (True)
        label.set_mnemonic_widget (entry)

        box = Gtk.HBox (False, 4)
        box.pack_start (label, False, True, 0)
        box.pack_start (entry, False, True, 0)
        return (entry, box)

    ## Interface methods
    def set_editable (self, editable):
        self.set_message ("", "editing", "white")
        if editable:
            self.vpu.clear()
            self.cursor_moved_cb (self.editor.get_buffer(), 0)
        else:
            self.vpu.load()
            self.editor_status.set_text ("")
        self.editor.mode.set_mode (self.vpu.vpu)

        self.run_button.set_sensitive (not editable)
        self.step_button.set_sensitive (not editable)
        self.continue_button.set_sensitive (not editable)
        self.clear_button.set_sensitive (not editable)
        if self.main_parent != None:
            self.main_parent.sync()

    def get_editable (self):
        return self.editor.get_editable()

    ## VPU bridge

    # cuts text into a list of instructions, like [(1, ["x", "rtn", "R2"]), ...]
    def get_program_code (self):
        buffer = self.editor.get_buffer()
        program = []
        line = 0
        while line < buffer.get_line_count():
            splits = buffer.split_line (line)
            line += 1
            if splits == None: break
            if len (splits) == 0: continue
            word = splits[0].word
            if splits[0].word[0] == '#':
                continue
            linep = []
            if word[-1] == ':':
                linep.append (word[:-1])
            else:
                linep.append ([])
                linep.append (word)
            for i in xrange (1, len (splits)):
                word = splits[i].word
                if word[0] == '#':
                    break
                else:
                    linep.append (word)
            program.append ((line, linep))
        return program

    def set_ram_model (self, model):
        for i in self.memory:
            i.set_model (model)
    def set_reg_model (self, model):
        self.registers.set_model (model)

    def set_ram_scroll (self, path):
        self.memory[-1].scroll_to_cell (path)
    def set_reg_scroll (self, path):
        self.registers.scroll_to_cell (path)

    def set_output_buffer (self, buffer):
        if buffer == None:
            buffer = Gtk.TextBuffer()
        self.output.set_buffer (buffer)

    def set_program_counter (self, value):
        self.counter.set_text (str (value))
        # set current line to the VPU one
        try: line = self.vpu.vpu.lines [value]
        except: pass
        else:
            self.editor.mode.set_current_line (line)
    def set_timer_counter (self, value):
        self.timer.set_text (str (value))

    def set_message (self, text, status, color, line = -1):
        if text == "": text = " "  # keep always same size
        self.message.set_text (text)
        message_box = self.message.get_parent()
        message_frame = message_box.get_parent()
        _color = Gdk.color_parse (color)
        message_box.modify_bg (Gtk.StateType.NORMAL, _color)
        message_frame.modify_bg (Gtk.StateType.NORMAL, _color)
        if status != None:
            self.vpu_status.set_text ("Status: " + status)
        self.editor.mode.set_current_line_color (color)
        if line != -1:
            self.editor.mode.set_current_line (line)

    # interface callbacks
    def on_edit_button_clicked (self, button):
        self.set_editable (True)
        self.editor.grab_focus()

    def on_load_button_clicked (self, button):
        self.set_editable (False)

    def on_run_button_clicked (self, button):
        self.vpu.run()

    def on_continue_button_clicked (self, button):
        self.vpu.cont()

    def on_step_button_clicked (self, button):
        self.vpu.step (self.step_value)

    def on_step_button_button_press_event (self, button, event):
        if event.button == 3:
            self.step_popup.popup (None, None, None, 3, event.time)
        return False

    def on_step_popup_activate (self, item, value):
        self.step_value = value
        self.step_button.set_label ("_Step " + str (value))

    def on_clear_button_clicked (self, button):
        self.editor.breakpoints = []
        self.editor.queue_draw()
        self.vpu.BreakP = []
        self.set_message ("All break points removed", None, "white")

    '''
    def on_lists_box_size_request (self, box, req):
        req.width = 200

    def on_lists_box_size_allocate (self, box, alloc):
        # allocate a little more space (2x) to memory-data table
        sizes = [ .25, .25, .50 ]
        children = box.get_children()
        children_nb = len (children)
        assert (len (sizes) == children_nb)
        alloc_width = alloc.width - (box.get_spacing() * (children_nb-1))
        x = alloc.x
        for i in xrange (children_nb):
            width = int (alloc_width * sizes[i])
            a = Gtk.gdk.Rectangle (x, alloc.y, width, alloc.height)
            children[i].size_allocate (a)
            x += width + box.get_spacing()
    '''

    def cursor_moved_cb (self, buffer, pos_ptr):
        if self.get_editable():
            iter = buffer.get_insert_iter()
            col = iter.get_line_offset() + 1
            lin = iter.get_line() + 1
            status = "Ln %d, Col %d" % (lin, col)
            self.editor_status.set_text (status)

    def buffer_modified_cb (self, buffer):
        if self.main_parent != None:
            self.main_parent.load_child_title (self)

    # file orders -- from menu
    def file_read (self, filename):
        self.set_editable (not test_mode)

        if filename == None:
            buffer = self.editor.get_buffer()
            buffer.delete (buffer.get_start_iter(), buffer.get_end_iter())
        else:
            if not self.editor.get_buffer().read (filename):
                msg = "Couldn't read from file: " + filename
                dialog = Gtk.MessageDialog (self.get_toplevel(),
                    Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
                    Gtk.MESSAGE_ERROR,
                    Gtk.ButtonsType.OK, msg)
                dialog.run()
                dialog.destroy()
                filename = None
                if test_mode: sys.exit (2)
        self.filename = filename
        return False

    def file_save (self, filename):
        if self.editor.get_buffer().write (filename):
            self.filename = filename
        else:
            msg = "Couldn't save to file: " + filename
            dialog = Gtk.MessageDialog (self.get_toplevel(),
                Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
                Gtk.MESSAGE_ERROR,
                Gtk.ButtonsType.OK, msg)
            dialog.format_secondary_text ("Check file permissions")
            dialog.run()
            dialog.destroy()

    def file_print (self):
        self.editor.print_text (self.main_parent.window, self.filename)

    # edit orders -- from menu
    def edit_undo (self):
        if not self.editor.get_editable(): return
        self.editor.get_buffer().undo()
    def edit_redo (self):
        if not self.editor.get_editable(): return
        self.editor.get_buffer().redo()

    def edit_can_undo (self):
        return self.editor.get_buffer().can_undo()
    def edit_can_redo (self):
        return self.editor.get_buffer().can_redo()

    def edit_cut (self):
        buffer = self.editor.get_buffer()
        clipboard = Gtk.clipboard_get()
        buffer.cut_clipboard (clipboard, self.editor.get_editable())
    def edit_copy (self):
        buffer = self.editor.get_buffer()
        clipboard = Gtk.clipboard_get()
        buffer.copy_clipboard (clipboard)
    def edit_paste (self):
        if not self.editor.get_editable(): return
        buffer = self.editor.get_buffer()
        clipboard = Gtk.clipboard_get()
        buffer.paste_clipboard (clipboard, None, True)

    def edit_kill_line (self):
        if not self.editor.get_editable(): return

        buffer = self.editor.get_buffer()
        line = buffer.get_iter_at_mark (buffer.get_insert()).get_line()
        start_it = buffer.get_iter_at_line (line)
        end_it = start_it.copy()
        end_it.forward_line()

        clipboard = Gtk.clipboard_get()
        clipboard.set_text (buffer.get_text (start_it, end_it, False))
        buffer.delete (start_it, end_it)

    def edit_yank (self):
        self.edit_paste_cb (item)

    def edit_mark_region (self):
        if not self.editor.get_editable(): return

        buffer = self.editor.get_buffer()
        it = buffer.get_iter_at_mark (buffer.get_insert())
        mark = buffer.get_mark ("emacs-mark")
        if mark:
            buffer.move_mark (mark, it)
        else:
            buffer.create_mark ("emacs-mark", it, True)

    def edit_kill_region (self):
        if not self.editor.get_editable(): return

        buffer = self.editor.get_buffer()
        buffer.delete_selection (True)

    def edit_copy_region_as_kill (self):
        self.edit_cut_cb (item)

    def edit_line_home (self):
        buffer = self.editor.get_buffer()
        it = buffer.get_iter_at_mark (buffer.get_insert())
        it.set_line_offset(0)
        buffer.place_cursor (it)

    def edit_line_end (self):
        buffer = self.editor.get_buffer()
        it = buffer.get_iter_at_mark (buffer.get_insert())
        it.forward_to_line_end()
        buffer.place_cursor (it)

    def edit_buffer_home (self):
        buffer = self.editor.get_buffer()
        it = buffer.get_start_iter()
        buffer.place_cursor (it)

    def edit_buffer_end (self):
        buffer = self.editor.get_buffer()
        it = buffer.get_end_iter()
        buffer.place_cursor (it)

    def edit_delete_right_char (self):
        if not self.editor.get_editable(): return
        buffer = self.editor.get_buffer()
        start_it = buffer.get_iter_at_mark (buffer.get_insert())
        end_it = start_it.copy()
        end_it.forward_char()
        buffer.delete (start_it, end_it)

# used as a ref to keep gtk loop alive until there are still windows open, and
# also to apply settings changes to all windows.
windows = []

class Window:
    def __init__ (self, filenames = [], interface = None):
        builder = builder_from_file ("ui/window.ui")
        if builder == None: return

        recents_menu = Gtk.RecentChooserMenu()
        recents_menu.set_show_numbers (True)
        recents_menu.set_local_only (True)
        recents_menu.set_sort_type (Gtk.RecentSortType.MRU)
        recents_menu.set_limit (10)
        filter = Gtk.RecentFilter()
        filter.add_pattern ("*.apoo")
        recents_menu.set_filter (filter)
        recents_menu.connect ("item-activated", self.on_file_open_recent_item_activate)
        item = builder.get_object ("file_open_recent")
        item.set_submenu (recents_menu)

        self.file_menu = builder.get_object ("file_menu")
        self.edit_menus = []
        for i in [1,2]:
            self.edit_menus.append (builder.get_object ("edit_item" + str(i)))
        self.close_item = builder.get_object ("file_close")
        self.close_item2 = builder.get_object ("file_close2")

        self.window = builder.get_object ("window")
        if test_mode:
            self.window.set_title ("Apoo Tester")
        else:
            self.window.set_title ("Apoo Workbench")
        self.window.show()
        self.window.set_default_icon_name ("apoo")

        self.notebook = builder.get_object ("notebook")
        self.notebook_popup = None

        for i in filenames:
            self.open_file (i)
        if interface != None:
            self.add_child (interface)
        elif len (filenames) == 0:
            self.add_child (Interface (None))
        self.sync()
        self.sync_preferences()
        builder.connect_signals (self)

        global windows
        windows.append (self)

    ## Interface handling
    def get_child (self):
        return self.notebook.get_nth_page (self.notebook.get_current_page())

    def add_child (self, child):
        label = Gtk.HBox (False, 2)
        # close button based on GEdit -- make it small
        close_image = Gtk.Image()
        close_image.set_from_stock (Gtk.STOCK_CLOSE, Gtk.IconSize.MENU)
        close_button = Gtk.Button()
        close_button.add (close_image)
        close_button.set_relief (Gtk.ReliefStyle.NONE)
        close_button.set_focus_on_click (False)
        Gtk.rc_parse_string (
            "style \"zero-thickness\"\n" +
            "{\n" +
            "   xthickness = 0\n" +
            "   ythickness = 0\n" +
            "}\n" +
            "widget \"*.pagebutton\" style \"zero-thickness\""
        )
        close_button.set_name ("pagebutton")
        close_button.set_tooltip_text ("Close document")
        close_button.connect ("clicked", self.notebook_page_close_cb, child)
        close_button.connect ("style-set", self.notebook_close_button_style_set_cb)

        icon = Gtk.Image.new_from_stock (Gtk.STOCK_FILE, Gtk.IconSize.MENU)
        label.label = Gtk.Label ("")

        label.pack_start (icon, False, True, 0)
        label.pack_start (label.label, True, True, 0)
        label.pack_start (close_button, False, True, 0)
        label.show_all()

        page_num = self.notebook.append_page (child, label)
        self.notebook.set_current_page (page_num)
        self.load_child_title (child)
        self.notebook.set_tab_reorderable (child, True)
        self.notebook.set_tab_detachable (child, True)
        child.main_parent = self

    def close_child (self, child):
        self.notebook.remove_page (self.notebook.page_num (child))

    def open_file (self, filename):  # None for empty
        if filename != None:
            # close page if it is blank
            pages = self.notebook.get_children()
            if len (pages) > 0:
                page = pages [len (pages)-1]
                if page.filename == None and not page.editor.get_buffer().get_modified():
                    self.close_child (page)
            self.file_accessed (filename)
        self.add_child (Interface (filename))

    def save_file (self, ask, child = None):
        if child == None:
            child = self.get_child()
        filename = child.filename
        if filename == None:
            ask = True
        if ask:
            global default_dir
            dialog = Gtk.FileChooserDialog ("Save File", self.window, Gtk.FILE_CHOOSER_ACTION_SAVE,
                                            buttons = (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                                                       Gtk.STOCK_SAVE, Gtk.ResponseType.ACCEPT))
            if default_dir != None:
                dialog.set_current_folder (default_dir)
            filter = Gtk.FileFilter()
            filter.set_name ("Apoo programs")
            filter.add_pattern ("*.apoo")
            dialog.set_filter (filter)
            dialog.set_local_only (True)
            dialog.set_do_overwrite_confirmation (True)
            dialog.set_default_response (Gtk.ResponseType.ACCEPT)

            ret = dialog.run()
            if ret == Gtk.ResponseType.ACCEPT:
                default_dir = dialog.get_current_folder()
                filename = dialog.get_filename()
                if not filename.endswith (".apoo"):
                    filename += ".apoo"
                dialog.destroy()
            else:
                dialog.destroy()
                return False            

        child.file_save (filename)
        self.file_accessed (filename)
        if ask:
            self.load_child_title (child)
        return True

    def file_accessed (self, filename):
        manager = Gtk.recent_manager_get_default()
        data = { 'mime_type': "text/plain", 'app_name': "apoo", 'app_exec': "apoo",
                 'display_name': os.path.basename (filename), 'groups': ['apoo'],
                 'is_private': bool (False), 'description': "Apoo program" }
        uri = filename
        if filename[0] != '/':
            uri = os.path.join (os.getcwd(), filename)
        uri = "file:/" + uri
        manager.add_full (uri, data)

    def load_child_title (self, child):
        if child.filename == None:
            title = "(unsaved)"
        else:
            title = os.path.basename (child.filename)
        if child.editor.get_buffer().get_modified():
            title = "*" + title
        label = self.notebook.get_tab_label (child)
        label.label.set_text (title)

    ## Events callbacks
    def on_notebook_page_added (self, notebook, child, page_num):
        child.main_parent = self
        self.sync()

    def on_notebook_switch_page (self, notebook, page_ptr, page_num):
        # either removed or just a switch
        self.sync()

    def notebook_page_close_cb (self, button, child):
        if self.confirm_child_changes (child):
            self.close_child (child)

    def notebook_close_button_style_set_cb (self, button, prev_style):
        _, w, h = Gtk.icon_size_lookup(Gtk.IconSize.MENU)
        button.set_size_request (w+2, h+2)

    def notebook_get_page_at (self, x, y):  # utility for press button
        page_num = 0
        while (page_num < self.notebook.get_n_pages()):
            page = self.notebook.get_nth_page (page_num)
            label = self.notebook.get_tab_label (page)
            if label.window.is_visible():
                label_x, label_y = label.window.get_origin()
                alloc = label.get_allocation()
                label_x += alloc.x
                label_y += alloc.y
                if x >= label_x and x <= label_x+alloc.width and y >= label_y and y <= label_y+alloc.height:
                    return (page_num, page)
            page_num += 1
        return (-1, None)

    def on_notebook_button_press_event (self, notebook, event):
        if event.button == 3 and event.type == Gtk.gdk.BUTTON_PRESS:
            if self.notebook_popup == None:
                item = Gtk.MenuItem ("Move to New Window")
                item.connect ("activate", self.notebook_detach_child_cb)
                item.show()
                self.notebook_popup = Gtk.Menu()
                self.notebook_popup.append (item)
                self.notebook_popup.attach_to_widget (self.notebook, None)

            page_num, _ = self.notebook_get_page_at (event.x_root, event.y_root)
            if page_num != -1:
                self.notebook.set_current_page (page_num)
                self.notebook_popup.popup (None, None, None, 3, event.time)
        return False

    def notebook_detach_child_cb (self, item):
        child = self.get_child()
        self.close_child (child)
        Window (interface = child)

    def on_file_new_activate (self, item):
        self.open_file (None)

    def on_file_open_activate (self, item):
        dialog = Gtk.FileChooserDialog ("Open File", self.window, Gtk.FILE_CHOOSER_ACTION_OPEN,
            buttons = (Gtk.STOCK_CANCEL, Gtk.ResponseType.REJECT, Gtk.STOCK_OPEN, Gtk.ResponseType.ACCEPT))
        global default_dir
        if default_dir != None:
            dialog.set_current_folder (default_dir)
        filter = Gtk.FileFilter()
        filter.set_name ("Apoo programs")
        filter.add_pattern ("*.apoo")
        dialog.set_filter (filter)
        dialog.set_local_only (True)
        dialog.set_select_multiple (True)
        dialog.add_shortcut_folder (EXAMPLES_PATH)
        dialog.set_default_response (Gtk.ResponseType.ACCEPT)

        if dialog.run() == Gtk.ResponseType.ACCEPT:
            default_dir = dialog.get_current_folder()
            for i in dialog.get_filenames():
                self.open_file (i)
        dialog.destroy()

    def on_file_open_recent_item_activate (self, chooser):
        uri = chooser.get_current_uri()
        if len (uri) > 6 and uri[0:6] == "file:/":
            uri = uri[6:]
        self.open_file (uri)

    def on_file_save_activate (self, item):
        self.save_file (False)

    def on_file_save_as_activate (self, item):
        self.save_file (True)

    def on_file_print_activate (self, item):
        self.get_child().file_print()

    def on_file_close_activate (self, item):
        child = self.get_child()
        if self.confirm_child_changes (child):
            self.close_child (child)

    def on_file_quit_activate (self, item):
        if self.confirm_changes():
            self.window.destroy()

    def on_edit_undo_activate (self, item):
        self.get_child().edit_undo()
    def on_edit_redo_activate (self, item):
        self.get_child().edit_redo()

    def on_edit_cut_activate (self, item):
        self.get_child().edit_cut()
    def on_edit_copy_activate (self, item):
        self.get_child().edit_copy()
    def on_edit_paste_activate (self, item):
        self.get_child().edit_paste()

    def on_edit_kill_line_activate (self, item):
        self.get_child().edit_kill_line()
    def on_edit_yank_activate (self, item):
        self.get_child().edit_yank()
    def on_edit_mark_region_activate (self, item):
        self.get_child().edit_mark_region()
    def on_edit_kill_region_activate (self, item):
        self.get_child().edit_kill_region()
    def on_edit_copy_region_as_kill_activate (self, item):
        self.get_child().edit_copy_region_as_kill()
    def on_edit_buffer_home_activate (self, item):
        self.get_child().edit_buffer_home()
    def on_edit_buffer_end_activate (self, item):
        self.get_child().edit_buffer_end()
    def on_edit_line_home_activate (self, item):
        self.get_child().edit_line_home()
    def on_edit_line_end_activate (self, item):
        self.get_child().edit_line_end()
    def on_edit_delete_right_character_activate (self, item):
        self.get_child().edit_delete_right_char()

    def on_edit_preferences_activate (self, item):
        show_preferences()

    def show_file_text_dialog (self, title, path, filename):
        dialog = Gtk.Dialog (title, self.window,
                             buttons = (Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE))
        dialog.set_default_response (Gtk.ResponseType.CLOSE)
        dialog.connect ("response", self.close_file_text_dialog_cb)
        dialog.set_default_size (-1, 450)

        buffer = Gtk.TextBuffer()
        file = open (path+filename + ".txt", 'r')
        buffer.set_text (file.read())
        file.close()

        view = Gtk.TextView.new_with_buffer (buffer)
        view.set_editable (False)
        view.set_cursor_visible (False)
        set_monospace_font (view)

        window = Gtk.ScrolledWindow()
        window.set_policy (Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        window.set_shadow_type (Gtk.ShadowType.IN)
        window.add (view)

        dialog.vbox.pack_start (window, True, True, 0)
        dialog.show_all()  # not run() because we don't want it modal

    def close_file_text_dialog_cb (self, dialog, response):
        dialog.destroy()

    def on_help_interface_activate (self, item):
        if test_mode: doc = DOC_TESTER
        else: doc = DOC_APOO
        self.show_file_text_dialog ("Help - Interface", DOCS_PATH, doc)

    def on_help_assembly_activate (self, item):
        self.show_file_text_dialog("Help - Assembly", DOCS_PATH, DOC_ASSEMBLY)

    def on_help_about_activate (self, item):
        dialog = Gtk.AboutDialog()
        dialog.set_transient_for (self.window)
        dialog.set_name ("Apoo")
        dialog.set_version (VERSION)
        dialog.set_copyright("Licensed under the GNU General Public License")
        dialog.set_website ("http://www.ncc.up.pt/apoo")
        dialog.set_authors (["Rogerio Reis <rvr@ncc.up.pt>", "Nelma Moreira <nam@ncc.up.pt>",
                             "(main developers)", "",
                             "Ricardo Cruz <rpmcruz@alunos.dcc.fc.up.pt>", "(interface developer)"])
        dialog.run()
        dialog.destroy()

    def run_confirm_dialog (self, nb, content):
        if nb > 1:
            msg = "There are " + str (nb) + " documents unsaved.\n"
        else:
            msg = "Document modified. "
        msg += "Save changes?"
        dialog = Gtk.MessageDialog (self.window,
            Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
            Gtk.MessageType.QUESTION, Gtk.ButtonsType.NONE, msg)
        dialog.add_button ("Don't Save", Gtk.ResponseType.REJECT)
        dialog.add_button (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
        dialog.add_button (Gtk.STOCK_SAVE, Gtk.ResponseType.ACCEPT)
        if content != None:
            dialog.vbox.pack_start (content, True, True, 0)
            content.show_all()
        ret = dialog.run()
        dialog.destroy()
        return ret

    def confirm_child_changes (self, child):
        if not child.editor.get_buffer().get_modified():
            return True
        response = self.run_confirm_dialog (1, None)
        if response == Gtk.ResponseType.CANCEL:
            return False
        if response == Gtk.ResponseType.ACCEPT:
            return self.save_file (False, child)
        return True
    def confirm_changes (self):
        model = Gtk.ListStore (bool, str, int)
        editors = self.notebook.get_children()
        modified = 0
        for i in xrange (len (editors)):
            if editors[i].editor.get_buffer().get_modified():
                iter = model.append()
                name = editors[i].filename
                if name == None:
                    name = "(page " + str (self.notebook.page_num (editors[i])+1) + ")"
                model.set (iter, 0, True, 1, name, 2, i)
                modified += 1
        if modified == 0:
            return True

        view = Gtk.TreeView (model)
        view.set_headers_visible (False)
        view.get_selection().set_mode (Gtk.SelectionMode.NONE)
        view.set_search_column (1)

        renderer = Gtk.CellRendererToggle()
        renderer.connect ("toggled", self.confirm_filename_toggled_cb, model)
        view.connect ("row-activated", self.confirm_filename_activated_cb, model)
        column = Gtk.TreeViewColumn ("", renderer, active = 0)
        view.append_column (column)
        column = Gtk.TreeViewColumn ("Filename", Gtk.CellRendererText(), text = 1)
        view.append_column (column)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy (Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_shadow_type (Gtk.ShadowType.IN)
        scroll.set_size_request (-1, 80)
        scroll.add (view)

        response = self.run_confirm_dialog (modified, scroll)
        if response == Gtk.ResponseType.ACCEPT:
            iter = model.get_iter_first()
            while iter != None:
                value = model.get_value (iter, 0)
                if value:
                    i = model.get_value (iter, 2)
                    if not self.save_file (False, editors[i]):
                        return False
                iter = model.iter_next (iter) 
            return True
        return response == Gtk.ResponseType.REJECT
    def confirm_filename_toggle (self, model, iter):
        value = model.get_value (iter, 0)
        model.set (iter, 0, not value)
    def confirm_filename_toggled_cb (self, cell, path_str, model):
        iter = model.get_iter_from_string (path_str)
        self.confirm_filename_toggle (model, iter)
    def confirm_filename_activated_cb (self, view, path, col, model):
        iter = model.get_iter (path)
        self.confirm_filename_toggle (model, iter)

    def on_window_delete_event (self, window, event):
        return not self.confirm_changes()

    def on_window_destroy (self, window):
        global windows
        windows.remove (self)
        if len (windows) == 0:
            Gtk.main_quit()
        return False

    def sync_preferences (self):
        for i in self.notebook.get_children():
            i.sync_preferences()
        if preferences["emacs_keys"]:
            self.edit_menus[0].hide()
            self.edit_menus[1].show()
            self.close_item.hide()
            self.close_item2.show()
        else:
            self.edit_menus[0].show()
            self.edit_menus[1].hide()
            self.close_item.show()
            self.close_item2.hide()

    def sync (self):
        pages_nb = self.notebook.get_n_pages()
        editing = False
        if pages_nb > 0:
            editing = self.get_child().get_editable()

        items = self.file_menu.get_children()
        for i in xrange (len (items)):
            if i > 2 and i < len (items)-1:
                items[i].set_sensitive (pages_nb > 0)
        for j in self.edit_menus:
            menu = j.get_submenu()
            if menu != None:
                items = menu.get_children()
                for i in xrange (len (items)):
                    if i < len (items)-1:
                        items[i].set_sensitive (editing)

if __name__ == "__main__":
    # parse arguments at first
    filenames = []
    argv = sys.argv
    for i in xrange (1, len (argv)):
        if argv[i] == "--tester" or argv[i] == "-t":
            test_mode = True

        elif argv[i] == "--help" or argv[i] == "-h":
            print "Usage: " + argv[0] + " [OPTIONS] [FILENAME]"
            print "Options may be:"
            print "\t--tester, -t\tExecute-only mode"
            print "\t--help, -h\tShow this help text"
            print ""
            sys.exit (0)

        elif argv[i][0] == '-':
            print "Unrecognized argument: " + argv[i]
            print "For usage: " + argv[0] + " --help"
            sys.exit (1)
        else:
            filenames.append (argv[i])
    DATA_PATH = os.path.dirname (argv[0]) + "/"
    if DATA_PATH == "/":
        DATA_PATH = "./"

    if test_mode and len (filenames) == 0:
        print "Usage: " + argv[0] + " --tester filename"
        sys.exit (1)

    # load our own CSS settings
    css = Gtk.CssProvider()
    css.load_from_path('ui/style.css')
    style = Gtk.StyleContext()
    style.add_provider_for_screen(Gdk.Screen.get_default(), css,
        Gtk.STYLE_PROVIDER_PRIORITY_USER)

    # go on, now
    read_config()

    Window (filenames)

    Gtk.main()

    write_config()

