WebWays for Windows
===================

Start:   double-click WebWays.exe (or the Start-menu shortcut). A console window opens (it IS the app; closing it
         stops WebWays) and your browser opens the interface. Double-clicking again reopens the running instance.

Index node (optional):   WebWays.exe indexer serve --db index.db
Print the API token:     WebWays.exe token
Help:                    WebWays.exe --help

Your data
  Settings, publisher key, resume data   %LOCALAPPDATA%\WebWays
  Downloads                              %USERPROFILE%\Downloads\WebWays

Windows will ask whether to allow WebWays through the firewall the first time: allow "Private networks" so other
BitTorrent peers can connect. The web interface itself listens on 127.0.0.1 only and is not reachable from the network.

This build is not code-signed, so Windows SmartScreen may warn you ("Windows protected your PC"): choose
More info -> Run anyway, after verifying the download's SHA-256 against the value on the release page.

Licenses and source code
  WebWays is free software. The client and UI are GPL-3.0-or-later, the index node is AGPL-3.0-or-later, the listing
  protocol is Apache-2.0. Full texts and third-party notices are in the "licenses" folder next to this file.
  Complete corresponding source for this exact build: https://github.com/aryank2212/WebWays (see the commit shown
  in BUILD-INFO.txt).
