# TODO/RoadMap:

- [ ] move the logout button away from the language so nobody log outs accidentally
- [ ] think if an account page is needed?
- [ ] fix the bug where mgrs and lat/lon doesn't show accordingly
- [ ] fix the roles so the admin account is the only one that can delete
- [ ] CI/CD
- [ ] build and compile
- [ ] think about windows support?
- [ ] **[SECURITY]** WebSocket endpoint (`/ws`) accepts connections from any client on the network with no authentication — anyone who can reach the server can receive all live position and SOS alert data. maybe (re)introduce JWT authentication?
- [ ] tighten CORS allow_origins=['*'] in main.py
- [ ] add support for serial devices
- [ ] orphaned files are not being deleted
- [ ] think if db migration (maybe alembic?) makes sense
- [ ] pg_notify has no reconnect logic at the moment
- [ ] access tokens never expire (currently on purpose)
- [ ] CRC check has no integrity check
- [ ] endpoints accessible to any user not just admin (are we going to have other users?)
