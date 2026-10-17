export async function register() {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    const { deployment } = await import("./lib/deployment");
    deployment(); // Validate runtime secrets/origins without baking them into the build.
  }
}
