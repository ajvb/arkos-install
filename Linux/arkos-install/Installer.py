#!/usr/bin/env python

########################################################################
##
##  arkOS Installer for Linux
##  Copyright (C) 2013 Jacob Cook
##  jacob@citizenweb.is
##
##  Uses elements of Raspbmc Installer, (C) 2013 Sam Nazarko
##
##  This program is free software: you can redistribute it and/or modify
##  it under the terms of the GNU General Public License as published by
##  the Free Software Foundation, either version 3 of the License, or
##  (at your option) any later version.
##
##  This program is distributed in the hope that it will be useful,
##  but WITHOUT ANY WARRANTY; without even the implied warranty of
##  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
##  GNU General Public License for more details.
##
##  You should have received a copy of the GNU General Public License
##  along with this program.  If not, see <http://www.gnu.org/licenses/>.
##
########################################################################

import gtk
import json
import os
import socket
import sys
import xml.etree.ElementTree as ET

from gobject import idle_add, threads_init
from md5 import new
from Queue import Queue
from subprocess import check_output, Popen, PIPE, STDOUT
from sys import exit
from time import sleep
from threading import Thread
from urllib2 import urlopen, HTTPError

gtk.gdk.threads_init()


###################################################
##  Gatekeeping Functions
###################################################

def check_priv():
    # Make sure the user has the privileges necessary to run
    if os.geteuid() != 0 and os.path.exists('/usr/bin/gksudo'):
        Popen(["gksudo", "-D arkOS Installer", sys.executable, os.path.realpath(__file__)])
        os._exit(os.EX_CONFIG)
    elif os.geteuid() != 0 and os.path.exists('/usr/bin/kdesudo'):
        Popen(["kdesudo", "--comment 'arkOS Installer'", sys.executable, os.path.realpath(__file__)])
        os._exit(os.EX_CONFIG)
    elif os.geteuid() != 0:
        error_handler("You do not have sufficient privileges to run this program. Please run Installer.py, or 'sudo ./main.py' instead.")

def error_handler(msg, close=True):
    # Throw up an error with the appropriate message and quit the application
    message = gtk.MessageDialog(None, 0, gtk.MESSAGE_ERROR, gtk.BUTTONS_OK, msg)
    message.run()
    message.destroy()
    if close is True:
        os._exit(os.EX_CONFIG)

def success_handler(msg, close=False):
    # Throw up a success message
    message = gtk.MessageDialog(None, 0, gtk.MESSAGE_INFO, gtk.BUTTONS_OK, msg)
    message.run()
    message.destroy()
    if close is True:
        os._exit(os.EX_CONFIG)


class Installer:

    ###################################################
    ##  Window Operation Functions
    ###################################################

    def __init__(self):
        # Create choice window
        self.chdlg = gtk.Window(gtk.WINDOW_TOPLEVEL)
        self.chdlg.set_default_size(375, 200)
        self.chdlg.set_geometry_hints(self.chdlg, 375, 200)
        self.chdlg.set_border_width(20)
        self.chdlg.set_title("arkOS Installer")
        self.chdlg.set_icon_from_file(os.path.join(os.path.dirname(__file__), 'images/icon.png'))
        self.chdlg.set_position(gtk.WIN_POS_CENTER)
        self.chdlg.connect("destroy", lambda w: gtk.main_quit())

        vbox = gtk.VBox()
        labels = gtk.VBox()

        image = gtk.Image()
        image.set_from_file(os.path.join(os.path.dirname(__file__), 'images/header.png'))
        vbox.pack_start(image, False, True, 10)

        image = gtk.Image()
        image.set_from_stock(gtk.STOCK_HARDDISK, gtk.ICON_SIZE_BUTTON)
        bbox = gtk.HBox(False, 0)
        bbox.set_border_width(2)
        blabel = gtk.Label("Install arkOS to an SD card")
        button = gtk.Button()
        button.add(bbox)
        button.connect("clicked", self.create_installer)
        bbox.pack_start(image, False, False, 3)
        bbox.pack_start(blabel, False, False, 3)
        vbox.pack_start(button, True, True, 0)

        image = gtk.Image()
        image.set_from_stock(gtk.STOCK_NETWORK, gtk.ICON_SIZE_BUTTON)
        bbox = gtk.HBox(False, 0)
        bbox.set_border_width(2)
        blabel = gtk.Label("Search the network for arkOS devices")
        button = gtk.Button()
        button.add(bbox)
        button.connect("clicked", self.create_finder)
        bbox.pack_start(image, False, False, 3)
        bbox.pack_start(blabel, False, False, 3)
        vbox.pack_start(button, True, True, 0)

        vbox.show_all()
        self.chdlg.add(vbox)
        self.chdlg.show()

    def create_finder(self, btn):
        # Create finder window
        self.chdlg.hide()
        self.fidlg = gtk.Window(gtk.WINDOW_TOPLEVEL)
        self.fidlg.set_default_size(640, 400)
        self.fidlg.set_geometry_hints(self.fidlg, 640, 400)
        self.fidlg.set_border_width(20)
        self.fidlg.set_title("arkOS Installer")
        self.fidlg.set_icon_from_file(os.path.join(os.path.dirname(__file__), 'images/icon.png'))
        self.fidlg.set_position(gtk.WIN_POS_CENTER)
        self.fidlg.connect("destroy", lambda w: gtk.main_quit())

        self.nodetype = None
        self.node = None
        vbox = gtk.VBox()

        # Create list of devices
        list_store = gtk.ListStore(int, str, str, str)
        tree_view = gtk.TreeView(list_store)

        cell = gtk.CellRendererText()
        column = gtk.TreeViewColumn("#", cell, text=0)
        column.set_sort_column_id(0)
        tree_view.append_column(column)
        cell = gtk.CellRendererText()
        column = gtk.TreeViewColumn("Name", cell, text=1)
        column.set_min_width(250)
        column.set_sort_column_id(1)
        tree_view.append_column(column)
        cell = gtk.CellRendererText()
        column = gtk.TreeViewColumn("IP Address", cell, text=2)
        column.set_min_width(100)
        column.set_sort_column_id(2)
        tree_view.append_column(column)
        cell = gtk.CellRendererText()
        column = gtk.TreeViewColumn("Genesis Status", cell, text=3)
        column.set_sort_column_id(3)
        tree_view.append_column(column)

        table = gtk.Table(1, 4, True)

        image = gtk.Image()
        image.set_from_stock(gtk.STOCK_FIND, gtk.ICON_SIZE_BUTTON)
        bbox = gtk.HBox(False, 0)
        bbox.set_border_width(2)
        blabel = gtk.Label("Scan")
        button = gtk.Button()
        button.add(bbox)
        button.connect("clicked", self.poll_nodes, vbox, list_store)
        bbox.pack_start(image, False, False, 3)
        bbox.pack_start(blabel, False, False, 3)
        table.attach(button, 0, 1, 0, 1)
        
        image = gtk.Image()
        image.set_from_stock(gtk.STOCK_STOP, gtk.ICON_SIZE_BUTTON)
        bbox = gtk.HBox(False, 0)
        bbox.set_border_width(2)
        blabel = gtk.Label("Shutdown")
        button = gtk.Button()
        button.add(bbox)
        button.connect("clicked", self.sig_node, 'shutdown')
        bbox.pack_start(image, False, False, 3)
        bbox.pack_start(blabel, False, False, 3)
        table.attach(button, 1, 2, 0, 1)

        image = gtk.Image()
        image.set_from_stock(gtk.STOCK_REFRESH, gtk.ICON_SIZE_BUTTON)
        bbox = gtk.HBox(False, 0)
        bbox.set_border_width(2)
        blabel = gtk.Label("Reboot")
        button = gtk.Button()
        button.add(bbox)
        button.connect("clicked", self.sig_node, 'reboot')
        bbox.pack_start(image, False, False, 3)
        bbox.pack_start(blabel, False, False, 3)
        table.attach(button, 2, 3, 0, 1)

        image = gtk.Image()
        image.set_from_stock(gtk.STOCK_REFRESH, gtk.ICON_SIZE_BUTTON)
        bbox = gtk.HBox(False, 0)
        bbox.set_border_width(2)
        blabel = gtk.Label("Reload Genesis")
        button = gtk.Button()
        button.add(bbox)
        button.connect("clicked", self.sig_node, 'reload')
        bbox.pack_start(image, False, False, 3)
        bbox.pack_start(blabel, False, False, 3)
        table.attach(button, 3, 4, 0, 1)

        tree_selection = tree_view.get_selection()
        tree_selection.connect("changed", self.choose_node, vbox, tree_view)
        scrolledw = gtk.ScrolledWindow()
        scrolledw.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
        scrolledw.add(tree_view)
        vbox.pack_start(scrolledw, True, True, 0)
        vbox.pack_start(table, False, True, 0)

        vbox.show_all()
        self.fidlg.add(vbox)
        self.fidlg.show()

    def create_installer(self, btn):
        # Create installer window
        self.chdlg.hide()
        self.installer = gtk.Assistant()
        self.installer.set_default_size(640, 400)
        self.installer.set_geometry_hints(self.installer, 640, 400)
        self.installer.set_title("arkOS Installer")
        self.installer.set_position(gtk.WIN_POS_CENTER)
        self.installer.connect("cancel", self.quit_now)
        self.installer.connect("close", self.quit)

        self.queue = Queue()
        self.mirror_name = "New York (United States)"
        self.mirror_link = "https://uspx.arkos.io"
        self.device = "null"

        # Initialize basic pages
        self.create_page0()
        self.create_page1()
        self.create_page2()
        self.create_page3()
        self.create_page4()
        self.create_page5()

        self.installer.show()

    def quit(self, installer):
        # Run this at the end of the process when the writing is done
        self.installer.destroy()
        gtk.main_quit()

    def quit_now(self, installer):
        # Run this when the user cancels or exits at a sensitive time
        message = gtk.MessageDialog(self.installer, gtk.DIALOG_MODAL, gtk.MESSAGE_WARNING, gtk.BUTTONS_YES_NO, "Are you sure you want to quit? The installation is not complete and you will not be able to use your SD card.\n\nIf a disk write operation is in progress, this will not be able to stop that process.")
        response = message.run()
        message.destroy()
        if response == gtk.RESPONSE_YES:
            self.installer.destroy()
            gtk.main_quit()
            os._exit(os.EX_OK)
        else:
            return


    ###################################################
    ##  Package and Hash Checking Functions
    ###################################################

    def md5sum(self):
        # Returns an md5 hash for the file parameter
        f = file('latest.tar.gz', 'rb')
        m = new()
        while True:
            d = f.read(8096)
            if not d:
                break
            m.update(d)
        f.close()
        pack_md5 = m.hexdigest()
        file_md5 = open('latest.tar.gz.md5.txt')
        compare_md5 = file_md5.read().decode("utf-8")
        file_md5.close()
        if not pack_md5 in compare_md5:
            return 0
        else:
            return 1

    def pkg_check(self, label):
        # If package exists, check authenticity then skip download if necessary
        if os.path.exists("latest.tar.gz"):
            label.set_text("<b>Package found in working directory!</b> Checking authenticity...")
            label.set_use_markup(gtk.TRUE)
            while gtk.events_pending():
                gtk.main_iteration()
            if os.path.exists("latest.tar.gz.md5.txt"):
                result = self.md5sum()
                if result == 0:
                    # the md5s were different. continue with download as is
                    label.set_text("Package found in working directory, but MD5 check failed. Redownloading...")
                    return 0
                else:
                    # the md5s were the same! skip the download.
                    label.set_text("Authentic package found in working directory. Skipping download...")
                    return 1
            else:
                dl_md5 = urlopen("https://uspx.arkos.io/latest.tar.gz.md5.txt")
                md5_File = open('latest.tar.gz.md5.txt', 'w')
                md5_File.write(dl_md5.read())
                md5_File.close()
                result = self.md5sum()
                if result == 0:
                    # the md5s were different. gotta redownload the package
                    label.set_text("Package found in working directory, but MD5 check failed. Redownloading...")
                    return 0
                else:
                    # the md5s were the same! skip the download.
                    label.set_text("Authentic package found in working directory. Skipping download...")
                    return 1
        return 0


    ###################################################
    ##  Functions to Manage User Choices
    ###################################################  

    def choose_mirror(self, element, choice):
        # Remember the chosen mirror
        if choice == "0":
            self.mirror_name = "New York (United States)"
            self.mirror_link = "https://uspx.arkos.io"
        else:
            self.mirror_name = "Amsterdam (The Netherlands)"
            self.mirror_link = "https://eupx.arkos.io"

        self.dl_label.set_text(self.mirror_name)
        self.link_label.set_text(self.mirror_link)

    def sig_node(self, btn, r):
        if self.node is None:
            error_handler('Please make a selection', close=False)
        elif self.nodetype.startswith('Unknown'):
            error_handler('This feature can only be used on arkOS systems that have Beacon enabled', close=False)
        else:
            self.authdlg = gtk.Dialog("Authenticate", None, 0, None)
            self.authdlg.set_border_width(20)
            label = gtk.Label("Give the username/password of a qualified user on the device")
            label.set_line_wrap(True)
            self.authdlg.vbox.pack_start(label, True, True, 0)
            table = gtk.Table(2, 2, True)
            ulabel = gtk.Label("Username")
            table.attach(ulabel, 0, 1, 0, 1)
            plabel = gtk.Label("Password")
            table.attach(plabel, 0, 1, 1, 2)
            uentry = gtk.Entry()
            table.attach(uentry, 1, 2, 0, 1)
            pentry = gtk.Entry()
            passwd = pentry.get_text()
            pentry.set_visibility(False)
            table.attach(pentry, 1, 2, 1, 2)

            image = gtk.Image()
            image.set_from_stock(gtk.STOCK_CANCEL, gtk.ICON_SIZE_BUTTON)
            bbox = gtk.HBox(False, 0)
            bbox.set_border_width(2)
            blabel = gtk.Label("Cancel")
            button = gtk.Button()
            button.add(bbox)
            button.connect("clicked", lambda w: self.authdlg.destroy())
            bbox.pack_start(image, False, False, 3)
            bbox.pack_start(blabel, False, False, 3)
            self.authdlg.action_area.add(button)

            image = gtk.Image()
            image.set_from_stock(gtk.STOCK_DIALOG_AUTHENTICATION, gtk.ICON_SIZE_BUTTON)
            bbox = gtk.HBox(False, 0)
            bbox.set_border_width(2)
            blabel = gtk.Label("OK")
            button = gtk.Button()
            button.add(bbox)
            button.connect("clicked", self.send_sig, r, self.node, uentry, pentry)
            bbox.pack_start(image, False, False, 3)
            bbox.pack_start(blabel, False, False, 3)
            self.authdlg.action_area.add(button)

            self.authdlg.vbox.add(table)
            self.authdlg.vbox.show_all()
            self.authdlg.show()

    def send_sig(self, btn, r, ip, user, passwd):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.connect((ip, 8765))
            sslSocket = socket.ssl(s)
            sslSocket.write(json.dumps({
                'request': r,
                'user': user.get_text(),
                'pass': passwd.get_text(),
                }))
            rsp = json.loads(sslSocket.read())
            if 'ok' in rsp['response']:
                success_handler('Signal to %s sent successfully.' % r)
                self.authdlg.destroy()
            else:
                error_handler('Authentification failed', close=False)
            s.close()
        except Exception, e:
            error_handler('There was an error processing your request.\n\n' + str(e), close=False)

    def poll_nodes(self, element, window, list_store):
        list_store.clear()
        num = 0
        nodes = []
        addrrange = '192.168.0.0/24'

        # Step 1: find all RPis on the network
        scan = check_output(['nmap', '-oX', '-', '-sn', addrrange])
        hosts = ET.fromstring(scan)
        ips = []
        rpis = hosts.findall('.//address[@vendor="Raspberry Pi Foundation"]/..')
        for rpi in rpis:
            ips.append(rpi.find('.//address[@addrtype="ipv4"]').attrib['addr'])

        # Step 2: scan these RPis for Beacon instances
        for ip in ips:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                s.connect((ip, 8765))
                sslSocket = socket.ssl(s)
                sslSocket.write(json.dumps({
                    'request': 'status'
                    }))
                rsp = json.loads(sslSocket.read())
                if 'ok' in rsp['response']:
                    nodes.append([num + 1, 
                        rsp['name'], 
                        ip, 
                        rsp['status']
                        ])
                s.close()
            except:
                nodes.append([num + 1,
                    'Unknown (Raspberry Pi)',
                    ip,
                    'Unknown'
                    ])
                s.close()

        # Step 3: format the list of RPis and statuses into the GUI list
        for node in nodes:
            list_store.append(node)

    def poll_devices(self, element, page, list_store):
        # Pull up the list of connected disks
        list_store.clear()
        self.installer.set_page_complete(page, False)
        num = 0
        fdisk = Popen(['fdisk', '-l'], stdout=PIPE).stdout.readlines()
        mounts = Popen(['mount'], stdout=PIPE).stdout.readlines()
        for lines in fdisk:
            if lines.startswith("/dev/") or lines.find("/dev/") == -1:
                continue
            dev = lines.split()[1].rstrip(":")
            for thing in mounts:
                if dev in thing.split()[0] and thing.split()[2] == '/':
                    break
            else:
                size = lines.split()[2]
                unit = lines.split()[3].rstrip(",")
                num = num + 1
                list_store.append([num, dev, size, unit])

    def choose_node(self, element, page, tree_view):
        # Remember the chosen node
        treeselection = tree_view.get_selection()
        model, iter = treeselection.get_selected()
        if iter:
            self.nodetype = model.get_value(iter, 1)
            self.node = model.get_value(iter, 2)
        else:
            self.nodetype = None
            self.node = None

    def choose_device(self, element, page, tree_view):
        # Remember the chosen device
        treeselection = tree_view.get_selection()
        model, iter = treeselection.get_selected()
        if iter:
            self.device = model.get_value(iter, 1)
            self.installer.set_page_complete(page, True)
            self.device_label.set_text(self.device)
        else:
            self.device = None
            self.installer.set_page_complete(page, False)

    def install_handler(self, element, page):
        # Redo the Summary page to give install info, and switch pages.
        self.installer.set_page_complete(page, True)
        self.installer.set_current_page(4)
        self.installer.commit()
        self.download_label.set_text("<b>Downloading image from " + self.mirror_name + "...</b>")
        self.download_label.set_use_markup(gtk.TRUE)
        override = self.pkg_check(self.download_label)

        if override == 0:
            # If no valid package was found, run the download and image writer threads
            download = Downloader(self.progressbar, self.queue, self.mirror_link, 'latest.tar.gz.md5.txt')
            download.start()
            while download.isAlive():
                while gtk.events_pending():
                    gtk.main_iteration()
            download_result = self.queue.get()
            if download_result != 200:
                error_handler("The file could not be downloaded. Please check your Internet connection. If the problem persists and your connection is fine, please contact the arkOS maintainers.\n\nHTTP Error " + str(download_result))
                return
            download = Downloader(self.progressbar, self.queue, self.mirror_link, 'latest.tar.gz')
            download.start()
            while download.isAlive():
                while gtk.events_pending():
                    gtk.main_iteration()
            download_result = self.queue.get()
            if download_result != 200:
                error_handler("The file could not be downloaded. Please check your Internet connection. If the problem persists and your connection is fine, please contact the arkOS maintainers.\n\nHTTP Error " + str(download_result))
                return
            self.download_label.set_text("Downloading image from " + self.mirror_name + "... <b>DONE</b>")
            self.download_label.set_use_markup(gtk.TRUE)

            md5error = self.md5sum()
            if md5error == 0:
                error_handler("Installation failed: MD5 hashes are not the same. Restart the installer and it will redownload the package. If this error persists, please contact the arkOS maintainers.")
                return

        self.imgwriter_label.set_text("<b>Copying image to " + self.device + "...</b>\n(This will take a few minutes depending on SD card size.)")
        self.imgwriter_label.set_use_markup(gtk.TRUE)
        self.progressbar.set_fraction(0.0)
        self.progressbar.set_text(" ")
        write = ImgWriter(self.queue, self.device)
        while write.isAlive():
            self.progressbar.pulse()
            while gtk.events_pending():
                gtk.main_iteration()
            sleep(0.1)
        write_result = self.queue.get()
        if write_result != False:
            error_handler("The disk writing process failed with the following error:\n\n" + write_result)
        self.imgwriter_label.set_text("Copying image to " + self.device + "... <b>DONE</b>")
        self.imgwriter_label.set_use_markup(gtk.TRUE)
        self.installer.set_current_page(5)


    ###################################################
    ##  Page Content Functions
    ###################################################   

    def create_page0(self):
        # Create introduction page
        vbox = gtk.VBox()
        vbox.set_border_width(5)
        self.installer.append_page(vbox)
        self.installer.set_page_title(vbox, "arkOS Installer")
        self.installer.set_page_type(vbox, gtk.ASSISTANT_PAGE_INTRO)
        self.greeting = gtk.Label("Welcome to the arkOS Installer! This program will guide you through installing the arkOS image to an SD card inserted into your computer.\n\nOnce you click Forward, your computer will start downloading the arkOS image from our servers in preparation for the install. Please make sure your computer is connected to the Internet before continuing.")
        self.greeting.set_line_wrap(True)
        vbox.pack_start(self.greeting, True, True, 0)
        vbox.show_all()
        self.installer.set_page_complete(vbox, True)

    def create_page1(self):
        # Create mirror chooser page
        vbox = gtk.VBox()
        vbox.set_border_width(5)
        self.installer.append_page(vbox)
        self.installer.set_page_title(vbox, "1 - Choose Mirror")
        self.installer.set_page_type(vbox, gtk.ASSISTANT_PAGE_CONTENT)
        label = gtk.Label("Choose the download mirror closest to your location.")
        usa = gtk.RadioButton(None, "New York (United States)")
        eur = gtk.RadioButton(usa, "Amsterdam (Netherlands)")
        usa.connect("clicked", self.choose_mirror, "0")
        eur.connect("clicked", self.choose_mirror, "1")
        vbox.pack_end(eur, True, True, 0)
        vbox.pack_end(usa, True, True, 0)
        label.set_line_wrap(True)
        vbox.pack_start(label, True, True, 0)
        vbox.show_all()
        self.installer.set_page_complete(vbox, True)

    def create_page2(self):
        # Create the page for choosing a device
        vbox = gtk.VBox()
        vbox.set_border_width(5)
        self.installer.append_page(vbox)
        self.installer.set_page_title(vbox, "2 - Choose Device")
        self.installer.set_page_type(vbox, gtk.ASSISTANT_PAGE_CONTENT)
        label = gtk.Label("Choose the appropriate device from the list below. Note that it is very important to choose the correct device! If you choose another one you may seriously damage your system.")
        label.set_line_wrap(True)

        # Create list of devices
        list_store = gtk.ListStore(int, str, str, str)
        tree_view = gtk.TreeView(list_store)

        cell = gtk.CellRendererText()
        column = gtk.TreeViewColumn("#", cell, text=0)
        column.set_sort_column_id(0)
        tree_view.append_column(column)
        cell = gtk.CellRendererText()
        column = gtk.TreeViewColumn("Device", cell, text=1)
        column.set_min_width(400)
        column.set_sort_column_id(1)
        tree_view.append_column(column)
        cell = gtk.CellRendererText()
        column = gtk.TreeViewColumn("Size", cell, text=2)
        column.set_min_width(100)
        column.set_sort_column_id(2)
        tree_view.append_column(column)
        cell = gtk.CellRendererText()
        column = gtk.TreeViewColumn("Unit", cell, text=3)
        column.set_sort_column_id(3)
        tree_view.append_column(column)

        self.poll_devices(self, vbox, list_store)
        button = gtk.Button("Refresh")
        button.connect("clicked", self.poll_devices, vbox, list_store)
        tree_view.connect("cursor_changed", self.choose_device, vbox, tree_view)

        # Make it scroll!
        vbox.pack_start(label, True, True, 0)
        scrolledw = gtk.ScrolledWindow()
        scrolledw.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
        scrolledw.add(tree_view)
        vbox.add(scrolledw)
        vbox.pack_end(button, False, True, 0)
        self.installer.set_page_complete(vbox, False)
        vbox.show_all()

    def create_page3(self):
        # Create the page showing the summary of chosen options
        vbox = gtk.VBox()
        vbox.set_border_width(5)
        self.installer.append_page(vbox)
        self.installer.set_page_title(vbox, "3 - Confirm")
        self.installer.set_page_type(vbox, gtk.ASSISTANT_PAGE_CONTENT)
        label = gtk.Label("Please confirm the details below. Once you click Start, the download will begin, then the selected device will be erased and data will be overwritten.\n\n<b>NOTE that there is no way to halt the writing process once it begins.</b>")
        label.set_use_markup(gtk.TRUE)
        label.set_line_wrap(True)
        vbox.pack_start(label, True, True, 0)

        table = gtk.Table(3, 2, True)
        vbox.add(table)

        down = gtk.Label("Download Mirror: ")
        table.attach(down, 0, 1, 0, 1)
        self.dl_label = gtk.Label(self.mirror_name)
        table.attach(self.dl_label, 1, 2, 0, 1)
        downlink = gtk.Label("Mirror Address: ")
        table.attach(downlink, 0, 1, 1, 2)
        self.link_label = gtk.Label(self.mirror_link)
        table.attach(self.link_label, 1, 2, 1, 2)
        dev = gtk.Label("Device: ")
        table.attach(dev, 0, 1, 2, 3)
        self.device_label = gtk.Label(self.device)
        table.attach(self.device_label, 1, 2, 2, 3)

        self.startbutton = gtk.Button("Start!")
        self.startbutton.connect("clicked", self.install_handler, vbox)
        vbox.pack_end(self.startbutton, False, True, 0)

        vbox.show_all()
        self.installer.set_page_complete(vbox, False)

    def create_page4(self):
        # Create the page that actually does all the work
        vbox = gtk.VBox()
        vbox.set_border_width(5)
        self.installer.append_page(vbox)
        self.installer.set_page_title(vbox, "Installing arkOS")
        self.installer.set_page_type(vbox, gtk.ASSISTANT_PAGE_CONTENT)
        self.download_label = gtk.Label(" ")
        self.imgwriter_label = gtk.Label(" ")
        vbox.pack_start(self.download_label, True, True, 0)
        vbox.pack_start(self.imgwriter_label, True, True, 0)
        self.progressbar = gtk.ProgressBar()
        vbox.pack_start(self.progressbar, False, False, 0)
        vbox.show_all()
        self.installer.set_page_complete(vbox, False)

    def create_page5(self):
        # Create the final page with successful message
        vbox = gtk.VBox()
        vbox.set_border_width(5)
        self.installer.append_page(vbox)
        self.installer.set_page_title(vbox, "Installation complete")
        self.installer.set_page_type(vbox, gtk.ASSISTANT_PAGE_SUMMARY)
        label = gtk.Label("Congratulations! Your image has been written to the SD card successfully.\n\nInsert the SD card into your Raspberry Pi and connect it to your router.\n\nSet up your server by opening your browser and connecting to Genesis at the following address:\n\n<b>http://arkOS:8000</b>\n\nThen follow the on-screen instructions!")
        label.set_line_wrap(True)
        label.set_use_markup(gtk.TRUE)
        vbox.pack_start(label, True, True, 0)
        vbox.show_all()
        self.installer.set_page_complete(vbox, True)


###################################################
##  Threads for Long Processes
###################################################  

class Downloader(Thread):
    """

    Downloads the file passed to it.
    Args: progressbar - the widget in the main progress window
          queue - the message processing queue to pass HTTP errors
          mirror - the URL for the chosen mirror
          filename - the name of the file on the server to download

    """

    def __init__(self, progressbar, queue, mirror_link, filename):
        Thread.__init__(self)
        self.progressbar = progressbar
        self.queue = queue
        self.mirror_link = mirror_link + "/"
        self.filename = filename

    def run(self):
        # Download the files and report their status
        link = self.mirror_link + self.filename
        try:
            dl_file = urlopen(link)
        except HTTPError, e:
            self.queue.put(e.code)
            return
        io_file = open(self.filename, 'w')
        self.size_read(dl_file, io_file, 8192)
        io_file.close()
        self.queue.put(200)

    def size_read(self, response, file, chunk_size):
        # Continually compare the amount downloaded with what is left to get
        # Then pass that data back to the main thread to update the progressbar
        total_size = response.info().getheader('Content-Length').strip()
        total_size = int(total_size)
        bytes_so_far = 0
        update = 0
        while 1:
            chunk = response.read(chunk_size)
            file.write(chunk)
            bytes_so_far += len(chunk)
            if not chunk:
                break
            self.update_progress(bytes_so_far, chunk_size, total_size)
        return bytes_so_far

    def update_progress(self, bytes_so_far, chunk_size, total_size):
        # Looped function to update the progressbar for download
        percent = float(bytes_so_far) / total_size
        idle_add(self.progressbar.set_fraction, percent)
        percent = round(percent*100, 2)
        idle_add(self.progressbar.set_text, "%0.1f of %0.1f MiB (%0.0f%%)" %
            (float(bytes_so_far)/1048576, float(total_size)/1048576, percent))
        return True

class ImgWriter(Thread):
    # Writes the downloaded image to disk
    def __init__(self, queue, device):
        Thread.__init__(self)
        self.device = device
        self.queue = queue
        self.start()

    def run(self):
        # Write the image and refresh partition
        unzip = Popen(['tar', 'xzOf', 'latest.tar.gz'], stdout=PIPE)
        dd = Popen(['dd', 'status=noxfer', 'bs=1M', 'of=' + self.device], stdin=unzip.stdout, stderr=PIPE)
        error = dd.communicate()[1]
        if "error" in error:
            self.queue.put(error)
        else:
            self.queue.put(False)
            Popen(['blockdev', '--rereadpt', self.device])


def main():
    check_priv()
    Installer()
    gtk.main()

if __name__ == '__main__':
    main()
