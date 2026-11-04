## Tile Server

The tile server requires **Node.js** to be installed on the system. It is recommended to use the latest stable version of Node.js.

The server loads its configuration from the `.env` file in the project root (`bee-with-me/.env`). Make sure this file defines `VITE_TILE_HOST` and `VITE_TILE_PORT`, for example:

```env
VITE_TILE_HOST=127.0.0.1
VITE_TILE_PORT=8081
```

Use the host and port values appropriate for your setup.

### Linux / macOS

#### 1. Installation

Navigate to the `tile-server` directory:

```bash
cd ~/bee-with-me/tile-server
```

Initialize the Node.js project only if `package.json` does not already exist:

```bash
npm init -y
```

Install the required packages:

```bash
npm install better-sqlite3 dotenv
```

#### 2. Starting the Tile Server

Navigate to the `tile-server` directory:

```bash
cd ~/bee-with-me/tile-server
```

Start the server:

```bash
node server.js
```

The tile server will listen on the host and port configured by `VITE_TILE_HOST` and `VITE_TILE_PORT` in the project-root `.env` file.

---

### Windows

#### 1. Installation

Open **PowerShell** and navigate to the `tile-server` directory. Update the path if your project is stored in a different location:

```powershell
cd "D:\Documents\Project\Rescuer Location\bee-with-me\tile-server"
```

Initialize the Node.js project only if `package.json` does not already exist:

```powershell
npm init -y
```

Install the required packages:

```powershell
npm install better-sqlite3 dotenv
```

#### 2. Starting the Tile Server

In PowerShell, navigate to the `tile-server` directory:

```powershell
cd "D:\Documents\Project\Rescuer Location\bee-with-me\tile-server"
```

Start the server:

```powershell
node server.js
```

The tile server will listen on the host and port configured by `VITE_TILE_HOST` and `VITE_TILE_PORT` in the project-root `.env` file.
