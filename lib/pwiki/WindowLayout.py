import sets

import wx

from StringOps import escapeForIni, unescapeForIni

from Configuration import isLinux

from wxHelper import LayerSizer


class WinLayoutException(Exception):
    pass

# def getOverallDisplaysSize():
def getOverallDisplaysClientSize():
    """
    Estimate the rectangle of the screen real estate with all
    available displays. This assumes that all displays have same
    resolution and are positioned in a rectangular shape.
    """
    # TODO: Find solution for multiple displays with taskbar always visible

    if wx.Display.GetCount() == 1:
        return wx.GetClientDisplayRect()

    # The following may be wrong if taskbar is always visible
    width = 0
    height = 0

    for i in xrange(wx.Display.GetCount()):
        d = wx.Display(i)
        
        rect = d.GetGeometry()
        width = max(width, rect.x + rect.width)
        height = max(height, rect.y + rect.height)

    return wx.Rect(0, 0, width, height)


def setWindowPos(win, pos=None, fullVisible=False):
    """
    Set position of a wx.Window, but ensure that the position is valid.
    If fullVisible is True, the window is moved to be full visible
    according to its current size. It is recommended to call
    setWindowSize first.
    """
    if pos is not None:
        currentX, currentY = pos
    else:
        currentX, currentY = win.GetPositionTuple()
        
#     screenX, screenY = getOverallDisplaysSize()
    clRect = getOverallDisplaysClientSize()
    
    # fix any crazy screen positions
    if currentX < clRect.x:
        currentX = clRect.x + 10
    if currentY < clRect.y:
        currentY = clRect.y + 10
    if currentX > clRect.width:
        currentX = clRect.width - 100
    if currentY > clRect.height:
        currentY = clRect.height - 100

    if fullVisible:
        sizeX, sizeY = win.GetSizeTuple()
        if (currentX - clRect.x) + sizeX > clRect.width:
            currentX = clRect.width - sizeX + clRect.x
        if (currentY - clRect.y) + sizeY > clRect.height:
            currentY = clRect.height - sizeY + clRect.y

    win.SetPosition((currentX, currentY))



def setWindowSize(win, size):
    """
    Set size of a wx.Window, but ensure that the size is valid
    """
    sizeX, sizeY = size

#     screenX, screenY = getOverallDisplaysSize()    
    clRect = getOverallDisplaysClientSize()

    # don't let the window be > than the size of the screen
    if sizeX > clRect.width:
        sizeX = clRect.width - 20
    if sizeY > clRect.height:
        sizeY = clRect.height - 20

    # set the size
    win.SetSize((sizeX, sizeY))


def setWindowClientSize(win, size):
    """
    Similar to setWindowSize(), but sets the client size of the window
    """
    sizeX, sizeY = size

#     screenX, screenY = getOverallDisplaysSize()    
    clRect = getOverallDisplaysClientSize()

    # don't let the window be > than the size of the screen
    if sizeX > clRect.width:
        sizeX = clRect.width - 20
    if sizeY > clRect.height:
        sizeY = clRect.height - 20

    # set the size
    win.SetClientSize((sizeX, sizeY))



#     m_sashCursorWE = new wxCursor(wxCURSOR_SIZEWE);
#     m_sashCursorNS = new wxCursor(wxCURSOR_SIZENS);

SASH_TOP = 0
SASH_RIGHT = 1
SASH_BOTTOM = 2
SASH_LEFT = 3
SASH_NONE = 100


class SmartSashLayoutWindow(wx.SashLayoutWindow):
    def __init__(self, *args, **kwargs):
        wx.SashLayoutWindow.__init__(self, *args, **kwargs)
        
        self.effectiveSashPos = 0
        self.minimalEffectiveSashPos = 0
        self.sashPos = 0
        self.centerWindow = None
        
        self.SetMinimumSizeX(1)
        self.SetMinimumSizeY(1)

        wx.EVT_SASH_DRAGGED(self, self.GetId(), self.OnSashDragged)

        if isLinux():
            self._CURSOR_SIZEWE = wx.StockCursor(wx.CURSOR_SIZEWE)
            self._CURSOR_SIZENS = wx.StockCursor(wx.CURSOR_SIZENS)
            wx.EVT_MOTION(self, self.MouseMotion)
            wx.EVT_LEAVE_WINDOW(self, self.OnMouseLeave)
        
    if isLinux():

        def MouseMotion(self, evt):
            if evt.Moving():
                x, y = evt.GetPosition()
                sashHit = self.SashHitTest(x, y)
                
                if sashHit == SASH_NONE:
                    self.SetCursor(wx.NullCursor)
                elif sashHit == SASH_LEFT or sashHit == SASH_RIGHT:
                    self.SetCursor(self._CURSOR_SIZEWE)
                elif sashHit == SASH_TOP or sashHit == SASH_BOTTOM:
                    self.SetCursor(self._CURSOR_SIZENS)
                    
            evt.Skip()
    
        def OnMouseLeave(self, evt):
            self.SetCursor(wx.NullCursor)
            evt.Skip()


    def setInnerAutoLayout(self, centerWindow):
        if self.centerWindow is not None:
            return

        self.centerWindow = centerWindow
        wx.EVT_SIZE(self, self.OnSize)


    def align(self, al):
        if al == wx.LAYOUT_TOP:
            self.SetOrientation(wx.LAYOUT_HORIZONTAL)
            self.SetAlignment(wx.LAYOUT_TOP)
            self.SetSashVisible(wx.SASH_BOTTOM, True)
        elif al == wx.LAYOUT_BOTTOM:
            self.SetOrientation(wx.LAYOUT_HORIZONTAL)
            self.SetAlignment(wx.LAYOUT_BOTTOM)
            self.SetSashVisible(wx.SASH_TOP, True)
        elif al == wx.LAYOUT_LEFT:
            self.SetOrientation(wx.LAYOUT_VERTICAL)
            self.SetAlignment(wx.LAYOUT_LEFT)
            self.SetSashVisible(wx.SASH_RIGHT, True)
        elif al == wx.LAYOUT_RIGHT:
            self.SetOrientation(wx.LAYOUT_VERTICAL)
            self.SetAlignment(wx.LAYOUT_RIGHT)
            self.SetSashVisible(wx.SASH_LEFT, True)


    def setSashPosition(self, pos):
        if self.GetOrientation() == wx.LAYOUT_VERTICAL:
            self.SetDefaultSize((pos, 1000))
        else:
            self.SetDefaultSize((1000, pos))
            
        self.sashPos = pos
        if pos >= self.minimalEffectiveSashPos:
            self.effectiveSashPos = pos
            
        parent = self.GetParent()
        sevent = wx.SizeEvent(parent.GetSize())
        parent.ProcessEvent(sevent)

    def getSashPosition(self):
        return self.sashPos


    def setMinimalEffectiveSashPosition(self, minPos):
        self.minimalEffectiveSashPos = minPos

    def getMinimalEffectiveSashPosition(self):
        return self.minimalEffectiveSashPos

    def setEffectiveSashPosition(self, ePos):
        # TODO Check bounds
        self.effectiveSashPos = ePos

    def getEffectiveSashPosition(self):
        return self.effectiveSashPos

    def isCollapsed(self):
        return self.getSashPosition() < self.minimalEffectiveSashPos

    def expandWindow(self, flag=True):
        if flag and self.isCollapsed():
            self.setSashPosition(self.effectiveSashPos)
        elif not flag and not self.isCollapsed():
            self.setSashPosition(1)

    def collapseWindow(self):
        if not self.isCollapsed():
            self.setSashPosition(1)



    def OnSashDragged(self, evt):
        # print "OnSashDragged", repr((evt.GetDragRect().width, evt.GetDragRect().height))

        if self.GetOrientation() == wx.LAYOUT_VERTICAL:
            self.setSashPosition(evt.GetDragRect().width)
        else:
            self.setSashPosition(evt.GetDragRect().height)

        evt.Skip()
        
    def OnSize(self, evt):
#         evt.Skip()
        if self.centerWindow is None:
            return
            
        wx.LayoutAlgorithm().LayoutWindow(self, self.centerWindow)


class WindowSashLayouter:
    """
    Helps layouting a couple of (SmartSashLayout)Window's in a main window
    """
    
    _RELATION_TO_ALIGNMENT = {
            "above": wx.LAYOUT_TOP,
            "below": wx.LAYOUT_BOTTOM,
            "left": wx.LAYOUT_LEFT,
            "right": wx.LAYOUT_RIGHT
    }

    def __init__(self, mainWindow, createWindowFunc):
        """
        mainWindow -- normally a frame in which the other windows
            should be layouted
        createWindowFunc -- a function taking a dictionary of properties
            (especially with a "name" property describing the name/type
            of window) and a parent wxWindow object to create a new window
            of requested type with requested properties
        """
        self.mainWindow = mainWindow
        self.createWindowFunc = createWindowFunc
#         self.centerWindowProps = None
        self.windowPropsList = []  # List of window properties, first window is
                # center window. List is filled during lay. definition


        # The following 4 are filled during layout realization

        self.directMainChildren = []  # List of window objects which are
                # direct children of the mainWindow. Destroying the windows
                # in this list resets the mainWindow for a new layout
                
        self.winNameToObject = {}  # Map from window name to wxWindow object
        self.winNameToSashWindow = {}  # Map from window name to enclosing
                # sash window object
        self.winNameToWinProps = {}

#         self.toRelayout = Set()  # Set of window objects for which the
#                 # wxLayoutAlgorithm.LayoutWindow() must be called


    def realize(self):
        """
        Called after a new layout is defined to realize it.
        """
        # TODO Allow calling realize() multiple times

        if len(self.windowPropsList) == 0:
            return  # TODO Error?

        centerWindowProps = self.windowPropsList[0]
        centerWindowName = centerWindowProps["name"]

        for pr in self.windowPropsList[1:]:
            winName = pr["name"]
            
            relTo = pr["layout relative to"]
            if relTo == centerWindowName:
                enclWin = self.mainWindow
            else:
                try:
                    enclWin = self.winNameToSashWindow[relTo]
                except KeyError:
                    enclWin = self.mainWindow

            sashWin = SmartSashLayoutWindow(enclWin, -1,
                wx.DefaultPosition, (30, 30), wx.SW_3DSASH)
            objWin = self.createWindowFunc(pr, sashWin)

            if objWin is None:
                sashWin.Destroy()
                continue

            relation = pr["layout relation"]
            
            sashPos = int(pr.get("layout sash position", "60"))
            sashEffPos = int(pr.get("layout sash effective position", "60"))

            sashWin.align(self._RELATION_TO_ALIGNMENT[relation])
            sashWin.setMinimalEffectiveSashPosition(5)  # TODO Configurable?
#             pos = self.getConfig().getint("main", "splitter_pos", 170)
#     
#             self.treeSashWindow.setSashPosition(pos)
            sashWin.setSashPosition(sashPos)
            sashWin.setEffectiveSashPosition(sashEffPos)

            self.winNameToObject[winName] = objWin
            self.winNameToSashWindow[winName] = sashWin
            self.winNameToWinProps[winName] = pr

            if enclWin is self.mainWindow:
                self.directMainChildren.append(sashWin)
            else:
                enclWin.setInnerAutoLayout(self.winNameToObject[relTo])
#                 self.toRelayout.add((enclWin, self.winNameToObject[relTo]))


        # Create center window
        winName = centerWindowProps["name"]
        objWin = self.createWindowFunc(centerWindowProps, self.mainWindow)
        if not objWin is None:
            self.winNameToObject[winName] = objWin
            self.directMainChildren.append(objWin)


    def getWindowForName(self, winName):
        """
        Return window object for name. Call this only after realize().
        Returns None if window not in layouter
        """
        return self.winNameToObject.get(winName)
        
    def focusWindow(self, winName):
        """
        Set focus to window named winName
        """
        w = self.getWindowForName(winName)
        
        if w is None:
            return
        
        w.SetFocus()


    def isWindowCollapsed(self, winName):
        sashWin = self.winNameToSashWindow.get(winName)
        if sashWin is None:
            return True

        return sashWin.isCollapsed()


    def expandWindow(self, winName, flag=True):
        sashWin = self.winNameToSashWindow.get(winName)
        if sashWin is None:
            return
            
        return sashWin.expandWindow(flag)

    def collapseWindow(self, winName):
        sashWin = self.winNameToSashWindow.get(winName)
        if sashWin is None:
            return
            
        return sashWin.collapseWindow()


    def updateWindowProps(self, winProps):
        """
        Update window properties, esp. layout information
        """
#         if winProps is None:
#             return

        sashWindow = self.winNameToSashWindow.get(winProps["name"])
        if sashWindow is None:
            # Delete any sash window positions
            winProps.pop("layout sash position", None)
            winProps.pop("layout sash effective position", None)
        else:
            winProps["layout sash position"] = str(sashWindow.getSashPosition())
            winProps["layout sash effective position"] = \
                    str(sashWindow.getEffectiveSashPosition())


    def cleanMainWindow(self, excluded=()):
        """
        Destroy all direct children of mainWindow which were created here
        to allow a new layout.
        
        excluded -- Sequence or set of window objects which shoudl be preserved
        """
        for w in self.directMainChildren:
            if (w not in excluded) and (w.GetParent() is self.mainWindow):
                w.Destroy()


    def layout(self):
        """
        Called after a resize of the main or one of the subwindows if necessary
        """
        if len(self.windowPropsList) == 0:
            return

        wx.LayoutAlgorithm().LayoutWindow(self.mainWindow,
                self.winNameToObject[self.windowPropsList[0]["name"]])


#     def setCenterWindowProps(self, winProps):
#         """
#         Set window (its properties) which occupies the remaining space
#         in the main window
#         """
#         self.centerWindowProps = winProps

    def addWindowProps(self, winProps):
        """
        Add window props of new window which should be layed out.
        winProps is then owned by addWindowProps, do not reuse it.
        """
        relTo = winProps.get("layout relative to")
        if relTo is None:
            if len(self.windowPropsList) > 0:
                raise WinLayoutException(u"All except first window must relate "
                        u"to another window. %s is not first window" %
                        winProps["name"])
            
            self.windowPropsList.append(winProps)
        else:
            relation = winProps.get("layout relation")
            if relation not in ("above", "below", "left", "right"):
                raise WinLayoutException((u"Window %s must relate to previously "
                            u"entered window") % winProps["name"])
            # Check if relTo relates to already entered window
            for pr in self.windowPropsList:
                if pr["name"] == relTo:
                    # Valid
                    self.windowPropsList.append(winProps)
                    break
            else:
                raise WinLayoutException((u"Window %s must relate to previously "
                            u"entered window") % winProps["name"])
        

    def getWinPropsForConfig(self):
        """
        Return a string from the winProps to write to configuration
        """
        result = []
        for pr in self.windowPropsList:
            self.updateWindowProps(pr)
            result.append(winPropsToString(pr))
        
        return ";".join(result)
        
    def setWinPropsByConfig(self, cfstr):
        """
        Create window properties by a string cfstr as returned
        by getWinPropsForConfig(). This method is an alternative to
        addWindowProps().
        """
        for ps in cfstr.split(";"):
            winProps = stringToWinprops(ps)
            self.addWindowProps(winProps)




def winPropsToString(winProps):
    return "&".join([escapeForIni(k, ";:&") + ":" + escapeForIni(v, ";:&")
            for k, v in winProps.iteritems()])


def stringToWinprops(s):
    if type(s) is unicode:
        s = str(s)

    items = [(unescapeForIni(item.split(":", 1)[0]),
            unescapeForIni(item.split(":", 1)[1])) for item in s.split("&")]
    
    result = {}
    for k, v in items:
        result[k] = v
        
    return result


class LayeredControlPresenter:
    """
    Controls appearance of multiple controls laying over each other in
    one panel or notebook.
    """
    def __init__(self):
        self.subControls = {}
        self.lastVisibleCtrlName = None
        self.visible = False
        self.shortTitle = ""
        self.longTitle = ""

    def setSubControl(self, scName, sc):
        self.subControls[scName] = sc

    def getSubControl(self, scName):
        return self.subControls.get(scName)


    def switchSubControl(self, scName):
        """
        Make the chosen subcontrol visible, all other invisible
        """
        try:
            if self.visible and self.lastVisibleCtrlName != scName:
                # First show subControl scName, then hide the others
                # to avoid flicker
                self.subControls[scName].setLayerVisible(True)
                for n, c in self.subControls.iteritems():
                    if n != scName:
                        c.setLayerVisible(False)

            self.lastVisibleCtrlName = scName
            self.setTitle(self.shortTitle)

        except KeyError:
            traceback.print_exc()

    def getCurrentSubControlName(self):
        return self.lastVisibleCtrlName
        
    def getCurrentSubControl(self):
        return self.subControls.get(self.lastVisibleCtrlName)


    def setLayerVisible(self, vis):
        if self.visible == vis:
            return
        
        if vis:
            for n, c in self.subControls.iteritems():
                c.setLayerVisible(n == self.lastVisibleCtrlName)
        else:
            for c in self.subControls.itervalues():
                c.setLayerVisible(False)

        self.visible = vis
        
    def close(self):
        for c in self.subControls.itervalues():
            c.close()

        
    def SetFocus(self):
        self.subControls[self.lastVisibleCtrlName].SetFocus()
        
    def setTitle(self, shortTitle):
        self.shortTitle = shortTitle
        self.longTitle = shortTitle

    def getShortTitle(self):
        return self.shortTitle

    def getLongTitle(self):
        return self.longTitle


class LayeredControlPanel(wx.Panel, LayeredControlPresenter):
    """
    A layered presenter which is itself a wx.Panel and contains
    the subcontrols.
    """
    def __init__(self, parent, id=-1):
        wx.Panel.__init__(self, parent, id, style=wx.NO_BORDER)
        LayeredControlPresenter.__init__(self)
        
        self.SetSizer(LayerSizer())


    def setSubControl(self, scName, sc):
        # TODO handle case if existing sc is replaced
        LayeredControlPresenter.setSubControl(self, scName, sc)
        self.GetSizer().Add(sc)


    def switchSubControl(self, scName, gainFocus=False):
        """
        Make the chosen subcontrol visible, all other invisible
        """
        try:
            # First show subControl scName, then hide the others
            # to avoid flicker
            if self.visible and self.lastVisibleCtrlName != scName:
                self.subControls[scName].setLayerVisible(True)
            
            self.subControls[scName].Show(True)

            for n, c in self.subControls.iteritems():
                if n != scName:
                    if self.visible:
                        c.setLayerVisible(False)
                    c.Show(False)

            if gainFocus:
                self.subControls[scName].SetFocus()

            self.lastVisibleCtrlName = scName
            self.setTitle(self.shortTitle)   #?
        except KeyError:
            traceback.print_exc()

    def SetFocus(self):
        try:
            self.subControls[self.lastVisibleCtrlName].SetFocus()
        except KeyError:
            wx.Panel.SetFocus(self)




            
