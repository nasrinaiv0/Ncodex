import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

const app = fs.readFileSync("web/app.js", "utf8");
const pickerBlock = app.slice(app.indexOf("  function savedHumanoid()"), app.indexOf("  const money ="));
const switchBlock = app.slice(app.indexOf("  function setHumanoid("), app.indexOf("  function setExpression("));
assert.ok(pickerBlock.startsWith("  function savedHumanoid()"), "Character preference block missing");
assert.ok(switchBlock.startsWith("  function setHumanoid("), "Character switch block missing");
const markup = fs.readFileSync("web/index.html", "utf8");
const skins = fs.readFileSync("web/humanoids.css", "utf8");

function createHarness(initial = null) {
  const data = new Map(initial ? [["ncodex.humanoid.v1", initial]] : []);
  const nodes = Object.fromEntries([
    "hero-bot-name", "chat-bot-name", "nav-bot-label", "action-bot-label",
    "hero-talk-label", "robot-emblem", "initial-bot-label", "initial-bot-message",
    "humanoid-stage", "chat-input"
  ].map(id => [id,{textContent:"", attrs:{}, setAttribute(k,v){this.attrs[k]=v;}}]));
  const buttons = ["dirk","ej","dirk","ej","dirk","ej"].map(name=>({
    dataset:{humanoid:name},attrs:{},active:false,
    classList:{toggle(){ }},listeners:{},
    setAttribute(k,v){this.attrs[k]=v;},
    addEventListener(k,fn){this.listeners[k]=fn;}
  }));
  const announcements=[];
  let page="home";
  const context={
    localStorage:{getItem(key){return data.get(key)||null;},setItem(k,v){data.set(k,v);}},
    document:{
      body:{dataset:{}},
      querySelectorAll(selector){assert.match(selector,/data-humanoid/);return buttons;},
    },
    chatBubble(role,message){announcements.push({role,message});}
  };
  context.$=(id)=>nodes[id]||null;
  vm.runInNewContext(pickerBlock+switchBlock+"\nglobalThis.__inspect = {state,humanoids};",context);
  return {context,nodes,buttons,data,announcements,get state(){return context.__inspect.state;}};
}

test("Two humanoids available with separate names and perspectives",()=>{
  const h=createHarness();
  assert.equal(h.state.humanoid,"dirk");
  assert.equal(h.nodes["chat-bot-name"].textContent,"DIRK");
  assert.equal(h.nodes["robot-emblem"].textContent,"D");
  assert.match(h.nodes["initial-bot-message"].textContent,/methodical|disciplined/);
  assert.match(h.nodes["humanoid-stage"].attrs["aria-label"],/Dirk|DIRK/);
  assert.equal(h.buttons[0].attrs["aria-pressed"],"true");
  assert.equal(h.buttons[1].attrs["aria-pressed"],"false");
  assert.equal(h.data.get("ncodex.humanoid.v1"),"dirk");
});

test("Switching to EJ updates all UI labels, active buttons, description and persists",()=>{
  const h=createHarness();
  h.context.__inspect.state.screen="chat";
  // The lexical switch function runs with a simulated DOM, like a mobile browser.
  vm.runInNewContext("setHumanoid('ej', true)",h.context);
  assert.equal(h.state.humanoid,"ej");
  for (const id of ["hero-bot-name","chat-bot-name","nav-bot-label"]) {
    assert.equal(h.nodes[id].textContent,"EJ");
  }
  assert.equal(h.nodes["robot-emblem"].textContent,"E");
  assert.equal(h.nodes["hero-talk-label"].textContent,"Talk to EJ");
  assert.equal(h.nodes["chat-input"].placeholder,"Ask EJ about trading…");
  assert.match(h.nodes["initial-bot-message"].textContent,/research/);
  assert.equal(h.data.get("ncodex.humanoid.v1"),"ej");
  assert.equal(h.buttons[0].attrs["aria-pressed"],"false");
  assert.equal(h.buttons[1].attrs["aria-pressed"],"true");
  assert.equal(h.announcements.length,1);
  assert.match(h.announcements[0].message,/EJ online/);
});

test("Saved EJ loads on next launch, invalid personas ignored",()=>{
  const h=createHarness("ej");
  assert.equal(h.state.humanoid,"ej");
  vm.runInNewContext("setHumanoid('unauthorized-version', true)",h.context);
  assert.equal(h.state.humanoid,"ej");
  assert.equal(h.data.get("ncodex.humanoid.v1"),"ej");
});

test("Both versions have selector controls in Home, Chat and Settings",()=>{
  assert.equal((markup.match(/data-humanoid="dirk"/g)||[]).length,3);
  assert.equal((markup.match(/data-humanoid="ej"/g)||[]).length,3);
  assert.match(markup,/aria-pressed="true"/);
  assert.match(markup,/id="chat-bot-name"/);
  assert.match(markup,/id="humanoid-avatar"/);
  assert.match(markup,/href="\/humanoids.css"/);
  assert.doesNotMatch(markup,/\bNOVA\b/);
});

test("Dirk/EJ have distinct robot shells and responsive mobile rules",()=>{
  assert.match(skins,/body\[data-humanoid="dirk"\] \.robot-head/);
  assert.match(skins,/body\[data-humanoid="ej"\] \.robot-head/);
  assert.match(skins,/body\[data-humanoid="dirk"\] \.robot-eyes i/);
  assert.match(skins,/body\[data-humanoid="ej"\] \.robot-eyes i/);
  assert.match(skins,/@media\(max-width:390px\)/);
  assert.match(skins,/prefers-reduced-motion/);
  assert.doesNotMatch(skins,/linear-gradient|radial-gradient/);
});

