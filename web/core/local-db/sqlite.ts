// import sqlite3InitModule from "@sqlite.org/sqlite-wasm";
import { sqlite3Worker1Promiser } from "@sqlite.org/sqlite-wasm";
import { createTables } from "./tables";

declare module "@sqlite.org/sqlite-wasm" {
  export function sqlite3Worker1Promiser(...args: any): any;
}

const log = console.log;
const error = console.error;

const SQL = {};
const start = async (sqlite3: any) => {
  log("Running SQLite3 version", sqlite3.version.libVersion);
  SQL.db = new sqlite3.oo1.DB("/mydb.sqlite3", "ct");
  createTables(SQL.db);
};

const initializeSQLiteMemory = async () => {
  try {
    log("Loading and initializing SQLite3 module...");
    const sqlite3 = await sqlite3InitModule({
      print: log,
      printErr: error,
    });
    log("Done initializing. Running demo...");
    await start(sqlite3);
  } catch (err) {
    error("Initialization error:", err.name, err.message);
  }
};

const initializeSQLite = async () => {
  if (SQL.db) {
    console.info("Instance already initialized");
    return;
  }
  try {
    log("Loading and initializing SQLite3 module...");

    const promiser = await new Promise((resolve) => {
      const _promiser = sqlite3Worker1Promiser({
        onready: () => resolve(_promiser),
      });
    });

    log("Done initializing. Running demo...");

    const configResponse = await promiser("config-get", {});
    log("Running SQLite3 version", configResponse.result.version.libVersion);

    const openResponse = await promiser("open", {
      filename: "file:mydb.sqlite3?vfs=opfs",
    });
    const { dbId } = openResponse;
    SQL.db = {
      dbId,
      exec: async (val) => {
        if (typeof val === "string") {
          val = { sql: val };
        }
        return promiser("exec", { dbId, ...val });
      },
    };
    log(
      "OPFS is available, created persisted database at",
      openResponse.result.filename.replace(/^file:(.*?)\?vfs=opfs$/, "$1")
    );
    // Your SQLite code here.
    await createTables(SQL.db);
  } catch (err) {
    if (!(err instanceof Error)) {
      err = new Error(err.result.message);
    }
    error(err.name, err.message);
  }
};

// initializeSQLite();

export { SQL, initializeSQLite };
