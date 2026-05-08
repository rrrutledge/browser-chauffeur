async function scrollAndStabilize(frame) {
  let prevHeight = 0, stableCount = 0;
  for (let pass = 0; pass < 30; pass++) {
    const info = await frame.evaluate(() => ({
      h: document.documentElement.scrollHeight,
      vh: window.innerHeight,
      sy: window.scrollY,
    }));
    await frame.evaluate(y => window.scrollTo(0, y), info.sy + Math.max(info.vh * 0.6, 300));
    await new Promise(r => setTimeout(r, 600));
    const after = await frame.evaluate(() => ({
      h: document.documentElement.scrollHeight,
      sy: window.scrollY,
      vh: window.innerHeight,
    }));
    const atBottom = after.sy + after.vh + 30 >= after.h;
    if (after.h === prevHeight && atBottom) {
      if (++stableCount >= 2) break;
    } else {
      stableCount = 0;
    }
    prevHeight = after.h;
  }
}
