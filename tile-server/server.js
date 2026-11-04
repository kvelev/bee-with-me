const http = require('http')
const fs = require('fs')
const path = require('path')
const Database = require('better-sqlite3')

require('dotenv').config({
  path: path.join(__dirname, '..', '.env')
})

const HOST = process.env.VITE_TILE_HOST;
const PORT = process.env.VITE_TILE_PORT;

const TILE_SERVER = `http://${HOST}:${PORT}`

const MAPS_DIR = path.join(__dirname, 'maps')

if (!fs.existsSync(MAPS_DIR)) {
  fs.mkdirSync(MAPS_DIR, { recursive: true })
}

let currentMap = null
let currentDb = null
let currentInfo = null

// ------------------------------------------------------------
// Извличане на наличните MBTiles файлове
// ------------------------------------------------------------

function getMaps() {
  return fs
    .readdirSync(MAPS_DIR)
    .filter(name =>
      name.toLowerCase().endsWith('.mbtiles')
    )
    .map(name => ({
      id: name,
      name: name.replace(/\.mbtiles$/i, ''),
      file: name,
    }))
}

// ------------------------------------------------------------
// Отваряне на MBTiles
// ------------------------------------------------------------

function openMap(fileName) {
  const safeName = path.basename(fileName)

  const fullPath = path.join(
    MAPS_DIR,
    safeName
  )

  if (!fs.existsSync(fullPath)) {
    throw new Error(
      `MBTiles файлът не съществува: ${safeName}`
    )
  }

  if (
    !safeName.toLowerCase().endsWith('.mbtiles')
  ) {
    throw new Error(
      'Позволени са само .mbtiles файлове'
    )
  }

  // Ако вече е отворен този файл,
  // не го отваряме отново.
  if (
    currentMap === safeName &&
    currentDb
  ) {
    return currentInfo
  }

  // Затваряме предишната база
  if (currentDb) {
    try {
      currentDb.close()
    } catch (e) {
      console.warn(
        'Грешка при затваряне на старата карта:',
        e
      )
    }

    currentDb = null
  }

  console.log('')
  console.log(
    'Отваряне на карта:',
    safeName
  )

  console.log(
    'Файл:',
    fullPath
  )

  // ----------------------------------------------------------
  // ВАЖНО:
  // readonly = true
  //
  // SQLite чете директно от диска.
  // Не зареждаме 12 GB в RAM.
  // ----------------------------------------------------------

  currentDb = new Database(
    fullPath,
    {
      readonly: true,
      fileMustExist: true,
    }
  )

  currentMap = safeName

  // ----------------------------------------------------------
  // Metadata
  // ----------------------------------------------------------

  const metadata = {}

  try {
    const rows =
      currentDb.prepare(`
        SELECT name, value
        FROM metadata
      `).all()

    for (const row of rows) {
      metadata[row.name] =
        row.value
    }
  } catch (e) {
    console.warn(
      'Няма metadata таблица:',
      e.message
    )
  }

  // ----------------------------------------------------------
  // Zoom
  // ----------------------------------------------------------

  let minZoom = 0
  let maxZoom = 22

  try {
    const row =
      currentDb.prepare(`
        SELECT
          MIN(zoom_level) AS minz,
          MAX(zoom_level) AS maxz
        FROM tiles
      `).get()

    if (row?.minz != null) {
      minZoom = Number(row.minz)
    }

    if (row?.maxz != null) {
      maxZoom = Number(row.maxz)
    }
  } catch (e) {
    console.warn(
      'Не могат да се прочетат zoom нивата:',
      e.message
    )
  }

  // ----------------------------------------------------------
  // Bounds
  // ----------------------------------------------------------

  let bounds = null

  if (metadata.bounds) {
    const values =
      String(metadata.bounds)
        .split(',')
        .map(Number)

    if (
      values.length === 4 &&
      values.every(Number.isFinite)
    ) {
      bounds = {
        minLon: values[0],
        minLat: values[1],
        maxLon: values[2],
        maxLat: values[3],
      }
    }
  }

  currentInfo = {
    id: safeName,
    name: safeName.replace(
      /\.mbtiles$/i,
      ''
    ),
    file: safeName,
    minZoom,
    maxZoom,
    bounds,
    metadata,
  }

  console.log(
    'Карта:',
    currentInfo.name
  )

  console.log(
    'Zoom:',
    minZoom,
    '-',
    maxZoom
  )

  console.log(
    'Bounds:',
    bounds
  )

  return currentInfo
}

// ------------------------------------------------------------
// MIME type
// ------------------------------------------------------------

function getMimeType(buffer) {
  if (!buffer || buffer.length < 4) {
    return 'application/octet-stream'
  }

  // JPEG FF D8 FF
  if (
    buffer[0] === 0xff &&
    buffer[1] === 0xd8 &&
    buffer[2] === 0xff
  ) {
    return 'image/jpeg'
  }

  // PNG
  if (
    buffer[0] === 0x89 &&
    buffer[1] === 0x50 &&
    buffer[2] === 0x4e &&
    buffer[3] === 0x47
  ) {
    return 'image/png'
  }

  // GIF
  if (
    buffer[0] === 0x47 &&
    buffer[1] === 0x49 &&
    buffer[2] === 0x46
  ) {
    return 'image/gif'
  }

  // WebP
  if (
    buffer.length >= 12 &&
    buffer.toString(
      'ascii',
      0,
      4
    ) === 'RIFF' &&
    buffer.toString(
      'ascii',
      8,
      12
    ) === 'WEBP'
  ) {
    return 'image/webp'
  }

  return 'application/octet-stream'
}

// ------------------------------------------------------------
// JSON response
// ------------------------------------------------------------

function sendJson(
  res,
  status,
  data
) {
  const json =
    JSON.stringify(data)

  res.writeHead(status, {
    'Content-Type':
      'application/json; charset=utf-8',

    'Cache-Control':
      'no-cache',
  })

  res.end(json)
}

// ------------------------------------------------------------
// Tile
// ------------------------------------------------------------

function getTile(
  z,
  x,
  y
) {
  if (!currentDb) {
    throw new Error(
      'Няма избрана карта'
    )
  }

  z = Number(z)
  x = Number(x)
  y = Number(y)

  if (
    !Number.isInteger(z) ||
    !Number.isInteger(x) ||
    !Number.isInteger(y)
  ) {
    return null
  }

  // ----------------------------------------------------------
  // OpenLayers използва XYZ:
  //
  // Y = 0 отгоре
  //
  // MBTiles използва TMS:
  //
  // Y = 0 отдолу
  //
  // Затова:
  //
  // tmsY = 2^z - 1 - xyzY
  // ----------------------------------------------------------

  const tmsY =
    Math.pow(2, z) - 1 - y

  if (x < 0 || tmsY < 0) {
    return null
  }

  const maxTile =
    Math.pow(2, z) - 1

  if (
    x > maxTile ||
    y > maxTile ||
    tmsY > maxTile
  ) {
    return null
  }

  const row =
    currentDb.prepare(`
      SELECT tile_data
      FROM tiles
      WHERE zoom_level = ?
        AND tile_column = ?
        AND tile_row = ?
      LIMIT 1
    `).get(
      z,
      x,
      tmsY
    )

  if (!row) {
    return null
  }

  return row.tile_data
}

// ------------------------------------------------------------
// HTTP server
// ------------------------------------------------------------

const server =
  http.createServer(
    (req, res) => {

      try {

        const url =
          new URL(
            req.url,
            `${TILE_SERVER}`
          )

        const pathname =
          decodeURIComponent(
            url.pathname
          )

        // ----------------------------------------------------
        // CORS
        // ----------------------------------------------------

        res.setHeader(
          'Access-Control-Allow-Origin',
          '*'
        )

        res.setHeader(
          'Access-Control-Allow-Methods',
          'GET, OPTIONS'
        )

        if (
          req.method === 'OPTIONS'
        ) {
          res.writeHead(204)
          res.end()
          return
        }

        // ----------------------------------------------------
        // GET /api/maps
        // ----------------------------------------------------

        if (
          pathname === '/api/maps'
        ) {
          sendJson(
            res,
            200,
            {
              maps: getMaps(),
              current:
                currentMap,
            }
          )

          return
        }

        // ----------------------------------------------------
        // GET /api/current
        // ----------------------------------------------------

        if (
          pathname === '/api/current'
        ) {
          sendJson(
            res,
            200,
            currentInfo ?? {
              current: null,
            }
          )

          return
        }

        // ----------------------------------------------------
        // GET /api/select/file.mbtiles
        // ----------------------------------------------------

        if (
          pathname.startsWith(
            '/api/select/'
          )
        ) {

          const file =
            pathname.substring(
              '/api/select/'.length
            )

          try {
            const info =
              openMap(file)

            sendJson(
              res,
              200,
              {
                success: true,
                map: info,
              }
            )

          } catch (e) {

            sendJson(
              res,
              400,
              {
                success: false,
                error: e.message,
              }
            )
          }

          return
        }

        // ----------------------------------------------------
        // GET /tiles/z/x/y.jpg
        // ----------------------------------------------------

        const tileMatch =
          pathname.match(
            /^\/tiles\/(\d+)\/(\d+)\/(\d+)(?:\.(jpg|jpeg|png|webp))?$/
          )

        if (tileMatch) {

          if (!currentDb) {
            res.writeHead(404)
            res.end()
            return
          }

          const z =
            Number(tileMatch[1])

          const x =
            Number(tileMatch[2])

          const y =
            Number(tileMatch[3])

          const tile =
            getTile(
              z,
              x,
              y
            )

          if (!tile) {

            // Прозрачен tile вместо 404
            res.writeHead(
              204,
              {
                'Cache-Control':
                  'public, max-age=3600',
              }
            )

            res.end()

            return
          }

          const mime =
            getMimeType(tile)

          res.writeHead(
            200,
            {
              'Content-Type': mime,

              'Content-Length':
                tile.length,

              'Cache-Control':
                'public, max-age=86400',

              'Access-Control-Allow-Origin':
                '*',
            }
          )

          res.end(tile)

          return
        }

        // ----------------------------------------------------
        // GET /
        // ----------------------------------------------------

        if (
          pathname === '/'
        ) {
          sendJson(
            res,
            200,
            {
              service:
                'MBTiles Tile Server',

              currentMap,

              endpoints: {
                maps:
                  '/api/maps',

                current:
                  '/api/current',

                select:
                  '/api/select/{file}.mbtiles',

                tiles:
                  '/tiles/{z}/{x}/{y}.jpg',
              },
            }
          )

          return
        }

        // ----------------------------------------------------
        // 404
        // ----------------------------------------------------

        sendJson(
          res,
          404,
          {
            error:
              'Not found',
          }
        )

      } catch (e) {

        console.error(
          'Server error:',
          e
        )

        sendJson(
          res,
          500,
          {
            error:
              e.message,
          }
        )
      }
    }
  )

server.listen(
  PORT,
  HOST,
  () => {

    console.log('')
    console.log(
      '===================================='
    )

    console.log(
      'MBTiles Tile Server'
    )

    console.log(
      `${TILE_SERVER}`
    )

    console.log(
      '===================================='
    )

    console.log(
      'Maps directory:',
      MAPS_DIR
    )

    console.log(
      'Available maps:',
      getMaps()
    )

    console.log('')
  }
)