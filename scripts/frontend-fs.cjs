// Windows can intermittently reject concurrent recursive mkdir calls in this
// workspace. Retry only generated frontend directories; preserve other errors.
const fs = require("node:fs");
const path = require("node:path");
const { setTimeout: delay } = require("node:timers/promises");
const frontend = path.resolve(__dirname, "../frontend");
const roots = [".next", "node_modules"].map((name) => path.join(frontend, name) + path.sep);
const original = fs.promises.mkdir.bind(fs.promises);
const originalCallback = fs.mkdir.bind(fs);
const originalSync = fs.mkdirSync.bind(fs);
function generated(target, options, error) {
  const resolved = typeof target === "string" ? path.resolve(target) : "";
  return error.code === "EPERM" && roots.some((root) => (resolved + path.sep).startsWith(root));
}
if (process.platform === "win32") {
  fs.promises.mkdir = async (target, options) => {
    try { return await original(target, options); }
    catch (error) {
      if (!generated(target, options, error)) throw error;
      for (const milliseconds of [20, 80, 200, 400]) {
        await delay(milliseconds);
        try { return originalSync(target, { ...(typeof options === "object" ? options : {}), recursive: true }); }
        catch (retryError) { if (retryError.code !== "EPERM") throw retryError; }
      }
      throw error;
    }
  };
  fs.mkdir = (target, options, callback) => {
    if (typeof options === "function") { callback = options; options = undefined; }
    return originalCallback(target, options, (error, created) => {
      if (!error || !generated(target, options, error)) return callback(error, created);
      fs.promises.mkdir(target, options).then((result) => callback(null, result), callback);
    });
  };
}
