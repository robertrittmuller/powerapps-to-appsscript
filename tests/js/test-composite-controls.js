const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');

function runtime(kind) {
  function element(tag='SPAN') {
    return {tagName:tag,style:{},attrs:{},textContent:'',listeners:{},
      setAttribute(key,value){this.attrs[key]=String(value);},getAttribute(key){return this.attrs[key]??null;},
      hasAttribute(key){return key in this.attrs;},removeAttribute(key){delete this.attrs[key];},
      addEventListener(event,fn){(this.listeners[event]??=[]).push(fn);},
      fire(event){for(const fn of this.listeners[event]||[])fn({stopPropagation(){}});}};
  }
  const el=element(kind==='Header'?'HEADER':'BUTTON'),parts={},errors=[];
  for(const key of ['title','subtitle','description','preview','header-image','card-content','card-header','logo','logo-action','profile','user-image','initials']) parts[key]=element();
  parts['logo-action'].setAttribute('data-fx-action','true');
  el.setAttribute('data-fx-composite',kind);
  el.querySelector=selector=>parts[(selector.match(/data-fx-part="([^"]+)"/)||[])[1]]||null;
  const document={querySelector:selector=>selector.includes('"Control"')?el:null,querySelectorAll:()=>[],getElementById:()=>null,addEventListener(){}};
  const ctx=vm.createContext({document,console:{error:(...args)=>errors.push(args.map(String).join(' '))}});ctx.window=ctx;
  vm.runInContext(fs.readFileSync(require.resolve('../../static/gas-runtime.js'),'utf8'),ctx);
  function update(values){ctx.FXRuntime.compositeControl(document,'Control',null,Object.fromEntries(Object.entries(values).map(([key,value])=>[key,()=>value])));}
  return {el,parts,errors,ctx,update};
}

test('card text, image ordering, contrast and disabled state update without replacing content',()=>{
  const {el,parts,errors,ctx,update}=runtime('ModernCard');
  assert.equal(ctx.FXRuntime.compositeControl.length,4);
  update({Title:'R&D <teams>',Subtitle:'Details',Description:'Literal <b>text</b>',Image:'data:image/svg+xml,test',
    Fill:'rgb(0,51,102)',TitleSize:18,SubtitleColor:'red',LayoutDirection:'Horizontal',ImagePlacement:'AfterHeader',ImagePosition:'Fit'});
  assert.equal(parts.title.textContent,'R&D <teams>');assert.equal(parts.description.textContent,'Literal <b>text</b>');
  assert.equal(parts.title.style.color,'#ffffff');assert.equal(parts.subtitle.style.color,'red');assert.equal(parts.title.style.fontSize,'18pt');
  assert.equal(el.getAttribute('data-fx-direction'),'horizontal');assert.equal(parts.preview.style.order,'2');assert.equal(parts.preview.style.objectFit,'contain');
  update({Title:'Updated',Description:'',Image:'',Fill:'rgb(255,255,255)',BorderRadius:0,DisplayMode:'View'});
  assert.equal(parts.title.textContent,'Updated');assert.equal(parts.description.hidden,true);assert.equal(parts.preview.hasAttribute('src'),false);
  assert.equal(parts.title.style.color,'#000000');assert.equal(el.style.borderRadius,'0px');assert.equal(el.disabled,true);
  assert.deepEqual(errors,[]);
});

test('header preserves identity and no-photo fallback while logo actions use only the logo',async()=>{
  const {el,parts,errors,ctx,update}=runtime('Header');
  update({Title:'Documents',Logo:'data:image/png,logo',LogoTooltip:'Home',UserName:'Dana Analyst',UserEmail:'dana@example.test',
    UserImage:'',TitleRole:'Heading2',Style:'Neutral'});
  assert.equal(parts.title.textContent,'Documents');assert.equal(parts.title.getAttribute('aria-level'),'2');
  assert.equal(parts.initials.textContent,'DA');assert.equal(parts.profile.getAttribute('title'),'Dana Analyst\ndana@example.test');
  assert.equal(parts['logo-action'].disabled,false);
  let clicked=0;ctx.bind('Control','OnSelectLogo',()=>{clicked++;},null);
  el.fire('click');await new Promise(setImmediate);assert.equal(clicked,0);
  parts['logo-action'].fire('click');await new Promise(setImmediate);assert.equal(clicked,1);
  update({Title:'Documents',Logo:'data:image/png,logo',UserName:'Dana Analyst',DisplayMode:'Disabled',IsProfilePictureVisible:false});
  assert.equal(parts.profile.hidden,true);parts['logo-action'].fire('click');await new Promise(setImmediate);assert.equal(clicked,1);
  update({Title:'Documents',UserName:'Dana Analyst',UserImage:'data:image/png,bad'});
  parts['user-image'].fire('error');assert.equal(parts.initials.hidden,false);assert.equal(parts['user-image'].hidden,true);
  update({Title:'Documents',UserName:'Dana Analyst',UserImage:'data:image/png,bad'});
  assert.equal(parts.initials.hidden,false);assert.deepEqual(errors,[]);
});

test('unsupported composite layout and image values remain runtime errors',()=>{
  const {errors,update}=runtime('ModernCard');
  update({LayoutDirection:'Diagonal'});assert.match(errors.pop(),/Unsupported card direction/);
  update({ImagePosition:'Tile'});assert.match(errors.pop(),/Unsupported card ImagePosition/);
  update({Image:'javascript:alert(1)'});assert.match(errors.pop(),/Unsupported image URL/);
  update({Title:'Valid'});assert.deepEqual(errors,[]);
});
