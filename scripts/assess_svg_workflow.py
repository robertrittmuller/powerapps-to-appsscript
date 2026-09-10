"""Exercise the pinned SVG app's reachable source image controls in Chromium.

Run: ./pfx2gas browser scripts/assess_svg_workflow.py
Unreachable exported screens are recorded separately; no navigation is invented.
"""
import hashlib
import json
import re
import time

from browser_check import OUT, REPO, control, run_case
from playwright.sync_api import expect, sync_playwright

NAME='public-svg-app'
SOURCE_SHA256='3a424b2a81c2afe0a079cad007cfa88f7686b3256ab34dd8d33fe09b79b5f4f0'


def svg_state(locator):
    return locator.evaluate('''async el => {
      await el.decode();
      const src=el.getAttribute('src'),xml=decodeURIComponent(src.slice(src.indexOf(',')+1));
      const doc=new DOMParser().parseFromString(xml,'image/svg+xml');
      if(doc.querySelector('parsererror')) throw new Error('Generated SVG is malformed');
      return {naturalWidth:el.naturalWidth,naturalHeight:el.naturalHeight,xml,
        text:[...doc.querySelectorAll('text')].map(node=>node.textContent.trim()),
        stroke:doc.querySelector('.progress-bar')?.getAttribute('stroke'),
        filled:doc.querySelectorAll('polygon.filled').length};
    }''')


def assert_offset(state,expected):
    # Compare the rendered numeric CSS value, allowing floating-point roundoff
    # without requiring JavaScript's text representation to match Python's.
    values=re.findall(r'stroke-dashoffset:\s*([\d.eE+\-]+)',state['xml'])
    assert values and abs(float(values[-1])-expected)<1e-6,{'offsets':values,'expected':expected}


def raster_state(locator):
    return locator.evaluate('''async image => {
      await image.decode();
      const canvas=document.createElement('canvas');canvas.width=image.naturalWidth;canvas.height=image.naturalHeight;
      const ctx=canvas.getContext('2d');ctx.drawImage(image,0,0);
      const pixels=ctx.getImageData(0,0,canvas.width,canvas.height).data;
      let colored=0,gray=0,orange=0,opaque=0;
      for(let i=0;i<pixels.length;i+=4){
        const [r,g,b,a]=pixels.slice(i,i+4);if(a<128)continue;opaque++;
        if(Math.max(r,g,b)-Math.min(r,g,b)>40)colored++;
        if(Math.max(r,g,b)-Math.min(r,g,b)<3 && r>=220 && r<=242)gray++;
        if(r>200 && g>60 && g<160 && b<90)orange++;
      }
      return {colored,gray,orange,opaque,colorRatio:colored/Math.max(1,colored+gray)};
    }''')


def painted(locator,predicate):
    # SVG CSS animations use the browser's rendering clock, independent of the
    # paused JavaScript timer clock. Observe pixels with a bounded real-time poll.
    deadline=time.monotonic()+5
    state={}
    while time.monotonic()<deadline:
        state=raster_state(locator)
        if predicate(state):return state
        time.sleep(.1)
    raise AssertionError({'paintedImage':state})


def main():
    source=REPO/'samples/real/svg-app.msapp'
    assert hashlib.sha256(source.read_bytes()).hexdigest()==SOURCE_SHA256
    steps=[]
    def check(name,action):
        try:
            action();steps.append({'id':name,'status':'pass'})
        except Exception as error:
            steps.append({'id':name,'status':'fail','error':str(error)});raise
    def journey(page,_backend):
        expect(page.locator('[data-screen="Screen1"]')).to_be_visible()
        text=control(page,'TextInput1');slider=control(page,'Slider1');rating=control(page,'Dropdown1')
        check('source-initial-text',lambda:expect(text).to_have_value('Hello World'))
        check('source-initial-slider',lambda:expect(slider).to_have_value('50'))
        check('source-rating-options',lambda:expect(rating.locator('option')).to_have_text(['1','2','3','4','5']))
        def initial_images():
            states={name:svg_state(control(page,name)) for name in ['Image1','Image1_1','Image1_2','Image1_3','Image1_4']}
            for name in states:
                expect(control(page,name)).to_have_css('object-fit','contain')
                expect(control(page,name)).to_have_css('background-color','rgba(0, 0, 0, 0)')
            assert all(state['naturalWidth']>0 and state['naturalHeight']>0 for state in states.values())
            assert states['Image1']['text']==['Hello World']
            assert states['Image1_1']['text']==['50']
            assert states['Image1_2']['filled']==1
            (OUT/NAME/'initial-images.json').write_text(json.dumps(states,indent=2)+'\n')
        check('all-five-initial-images-decode',initial_images)
        for value in ['Welcome aboard','Café 東京','R&D <teams> "ready"','']:
            text.fill(value)
            def text_image(value=value):
                assert svg_state(control(page,'Image1'))['text']==[value]
            check('text-image-'+(value or 'blank'),text_image)
        slider.focus();slider.press('Home')
        previous=0
        for value,color in [(0,'red'),(19,'red'),(20,'yellow'),(39,'yellow'),(40,'#bada55'),(59,'#bada55'),(60,'#00bcd4'),(100,'green')]:
            for _ in range(value-previous):slider.press('ArrowRight')
            previous=value
            def progress(value=value,color=color):
                expect(slider).to_have_value(str(value))
                state=svg_state(control(page,'Image1_1'))
                assert state['text']==[str(value)] and state['stroke']==color,state
                assert_offset(state,314-value*3.14)
            check('slider-image-'+str(value),progress)
        for value in ['5','2','4','1','3']:
            rating.select_option(label=value)
            check('rating-'+value,lambda value=value:expect(rating).to_have_value(value))
            def rating_image(value=value):
                assert svg_state(control(page,'Image1_2'))['filled']==int(value)
            check('rating-image-'+value,rating_image)
        def timer_state(value,label):
            assert page.evaluate("val('Timer1').value")==value
            expect(control(page,'Timer1')).to_have_text(label)
            for name in ['Image1_3','Image1_4']:
                state=svg_state(control(page,name))
                assert_offset(state,314-value/5000*314)
            assert svg_state(control(page,'Image1_3'))['text']==[str(value/1000).removesuffix('.0')+'s']
        check('timer-initial-label-and-image',lambda:timer_state(0,'00:00:00'))
        page.clock.run_for(2500)
        check('timer-halfway-label-and-images',lambda:timer_state(2500,'00:00:02'))
        page.clock.run_for(2500)
        check('timer-complete-label-and-images',lambda:timer_state(5000,'00:00:05'))
        def paint_text():
            text.fill('Hello World')
            pixels=painted(control(page,'Image1'),lambda state:state['orange']>20)
            (OUT/NAME/'painted-text.json').write_text(json.dumps(pixels,indent=2)+'\n')
        check('animated-text-paints-final-orange-caption',paint_text)
        paints={}
        for value,predicate in [(0,lambda state:state['gray']>2000 and state['colorRatio']<.01),
                                (50,lambda state:.47<state['colorRatio']<.53),
                                (100,lambda state:state['colored']>2000 and state['colorRatio']>.97)]:
            def paint_progress(value=value,predicate=predicate):
                slider.focus();slider.press('Home')
                for _ in range(value):slider.press('ArrowRight')
                paints[str(value)]=painted(control(page,'Image1_1'),predicate)
            check('progress-ring-painted-'+str(value),paint_progress)
        (OUT/NAME/'painted-progress.json').write_text(json.dumps(paints,indent=2)+'\n')
        def painted_rating():
            values=[]
            for value in ['1','3','5']:
                rating.select_option(label=value)
                # The source's brighten animation temporarily scales each star
                # to 1.2. Compare areas after its authored 0.5-second duration.
                time.sleep(.65)
                values.append(painted(control(page,'Image1_2'),lambda state:state['colored']>100))
            assert values[1]['colored']>values[0]['colored']*2.5,values
            assert values[2]['colored']>values[1]['colored']*1.5,values
            (OUT/NAME/'painted-ratings.json').write_text(json.dumps(values,indent=2)+'\n')
        check('rating-stars-paint-selected-count',painted_rating)
        page.clock.run_for(1000)
        check('timer-does-not-repeat',lambda:timer_state(5000,'00:00:05'))
        control(page,'Timer1').click();page.clock.run_for(1000)
        check('timer-restarts-on-click',lambda:timer_state(1000,'00:00:01'))
        control(page,'Timer1').focus();control(page,'Timer1').press('Space');page.clock.run_for(1000)
        check('timer-pauses-on-keyboard-space',lambda:timer_state(1000,'00:00:01'))
        control(page,'Timer1').press('Enter');page.clock.run_for(4000)
        check('timer-resumes-on-keyboard-enter',lambda:timer_state(5000,'00:00:05'))
        page.screenshot(path=str(OUT/NAME/'source-images-complete.png'),full_page=True)
        geometry={}
        for width,height in [(1440,900),(1024,768)]:
            viewport=str(width)+'x'+str(height)
            page.set_viewport_size({'width':width,'height':height})
            # Viewport resize delivery is asynchronous and is not advanced by
            # Playwright's JavaScript timer clock. Wait for its visible result.
            expect(page.locator('#fx-canvas')).to_have_css('width',str(width)+'px')
            page.clock.run_for(100)
            def ui(viewport=viewport):
                measurements=page.locator('[data-screen="Screen1"] [data-control]').evaluate_all('''els=>els.map(el=>{
                    const r=el.getBoundingClientRect(),cx=r.x+r.width/2,cy=r.y+r.height/2;
                    return {name:el.dataset.control,x:r.x,y:r.y,width:r.width,height:r.height,
                      hit:el.contains(document.elementFromPoint(cx,cy)),fontSize:parseFloat(getComputedStyle(el).fontSize)};
                })''')
                assert len(measurements)==9,measurements
                for box in measurements:
                    assert box['x']>=-1 and box['y']>=-1 and box['x']+box['width']<=width+1 and box['y']+box['height']<=height+1,box
                    assert box['width']>0 and box['height']>=29 and box['hit'],box
                geometry[viewport]=measurements
                text.focus();expect(text).to_be_focused();text.fill('Viewport '+viewport)
                assert svg_state(control(page,'Image1'))['text']==['Viewport '+viewport]
                slider.focus();slider.press('Home');slider.press('ArrowRight')
                assert svg_state(control(page,'Image1_1'))['text']==['1']
                rating.focus();rating.press('Home');rating.press('ArrowDown');rating.press('Tab')
                expect(rating).to_have_value('2')
                assert svg_state(control(page,'Image1_2'))['filled']==2
                painted(control(page,'Image1'),lambda state:state['orange']>20)
                page.screenshot(path=str(OUT/NAME/('ui-'+viewport+'.png')),full_page=True)
            check('visible-controls-and-keyboard-'+viewport,ui)
        (OUT/NAME/'ui-geometry.json').write_text(json.dumps(geometry,indent=2)+'\n')
        def reload():
            page.reload()
            expect(text).to_have_value('Hello World');expect(slider).to_have_value('50');expect(rating).to_have_value('1')
            assert svg_state(control(page,'Image1'))['text']==['Hello World']
            assert svg_state(control(page,'Image1_1'))['text']==['50']
            assert svg_state(control(page,'Image1_2'))['filled']==1
            timer_state(0,'00:00:00');page.clock.run_for(2500);timer_state(2500,'00:00:02')
        check('reload-restores-source-defaults-and-autostart',reload)
    with sync_playwright() as p:
        browser=p.chromium.launch()
        result=run_case(browser,NAME,source,journey,clock=True)
        browser.close()
    if result['status']=='pass' and (len(steps)!=41 or any(step['status']!='pass' for step in steps)):
        result.update(status='fail',error='Incomplete SVG workflow/paint/interaction checks')
    result.update(sourceAppId='svg-app',steps=steps,completeUsability='unassessed',
        assessmentScope='reachable Screen1 SVG decoding and paint, text/slider/rating changes, timer lifecycle, reload and landscape keyboard/geometry checks',
        interactionAssessment={'status':result['status'],'viewports':[[1440,900],[1024,768]],
            'sourceSizing':'source fixed 1366×768 landscape canvas scales with its aspect ratio',
            'accessibility':'source text input, slider and dropdown have no authored accessible names; screen-reader usability remains unassessed'},
        assessmentScriptSha256=hashlib.sha256((REPO/'scripts/assess_svg_workflow.py').read_bytes()).hexdigest(),
        sourceLimitations=['The export has no navigation from Screen1 to Screen2–Screen5. Their custom Environment action and offline-host actions are not exercised by this reachable UI journey.',
            'Literal control text inserted into static SVG text/tspan elements is XML-escaped as a ledgered repair; user-supplied markup in those text values renders literally.'])
    (OUT/NAME/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'steps':steps},indent=2))
    return int(result['status']!='pass')


if __name__=='__main__':
    raise SystemExit(main())
