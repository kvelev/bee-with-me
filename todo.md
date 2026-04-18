# TODO: 
 - move the logout button away from the language so nobody log outs accidentally
 - think if an account page is needed?
 - fix the bug where mgrs and lat/lon doesn't show accordingly
 - add the possibility to download the maps locally and update it
 - fix the roles so the admin account is the only one that can delete
 - CI/CD
 - build and compile
 - think about windows support?
 - harden security

1.2.0
  - Stale position indicator — if a device hasn't sent a frame in e.g. 10 min, the marker should grey out or show a warning.    
  Right now a dead device looks identical to a live one.
  - JWT refresh tokens — the current setup issues a token that eventually expires and the user just gets kicked out silently.                                                                                                    
  - Distance/bearing readout — click two markers (or marker + cursor) and show straight-line distance and bearing. High value
  for field coordinators with no extra infrastructure.