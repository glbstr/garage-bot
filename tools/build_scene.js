// Сборка картинок сцены для сайта студии «ГАРАЖ».
//
// Рисует утверждённую изометрическую сцену (скетч A41) и сохраняет в web/static:
//   scene.png      — сцена в родном разрешении (браузер увеличивает её без сглаживания);
//   scene-map.png  — карта предметов: R = номер предмета * 20, G = мигающий огонёк, B = свет лампы;
//   scene.json     — размеры и рамки кликабельных предметов;
//   og.png         — увеличенная картинка для превью ссылки в мессенджерах;
//   favicon.png    — иконка вкладки.
//
// Запуск (нужны Node.js и Playwright): node tools/build_scene.js
// Сайту на сервере этот скрипт не нужен: готовые картинки лежат в репозитории.
const {chromium} = require('playwright');
const fs = require('fs');
const path = require('path');
const OUT = path.join(__dirname, '..', 'web', 'static');

// Порядок важен: номер предмета в карте = позиция в этом списке + 1.
const IDS = ['screen', 'speakers', 'keys', 'address', 'contacts', 'prices', 'rec', 'guitar', 'mic', 'shelf'];

function drawScene(IDS) {
  const W = 320, H = 190, PAD = 5;
  const c = document.createElement('canvas'); c.width = W; c.height = H;
  const real = c.getContext('2d');
  const idMap = new Uint8Array(W * H), blinkMap = new Uint8Array(W * H), glowMap = new Uint8Array(W * H);
  let curId = 0, isBlink = false, isGlow = false;
  const tag = name => { curId = name ? IDS.indexOf(name) + 1 : 0; };
  const blink = v => { isBlink = v; };
  const glow = v => { isGlow = v; };
  // Обёртка над контекстом: рисует на холсте и параллельно ведёт карту предметов.
  const x = {
    set fillStyle(v) { real.fillStyle = v; this._s = v; },
    get fillStyle() { return this._s; },
    fillRect(X, Y, w, h) {
      real.fillRect(X, Y, w, h);
      const translucent = String(this._s).startsWith('rgba');
      const x0 = Math.max(0, Math.round(X)), y0 = Math.max(0, Math.round(Y));
      const x1 = Math.min(W, Math.round(X + w)), y1 = Math.min(H, Math.round(Y + h));
      for (let yy = y0; yy < y1; yy++) for (let xx = x0; xx < x1; xx++) {
        const i = yy * W + xx;
        if (translucent) { if (isGlow) glowMap[i] = 1; continue; } // тени и блики не меняют карту
        idMap[i] = curId; blinkMap[i] = isBlink ? 1 : 0; glowMap[i] = 0;
      }
    },
  };
  const BIG={'Г':['11111','10000','10000','10000','10000'],'А':['01110','10001','11111','10001','10001'],'Р':['11110','10001','11110','10000','10000'],'Ж':['10101','10101','01110','10101','10101']};
  // полигон без сглаживания
  function P(x,col,pts){let a=1e9,z=-1e9;pts.forEach(q=>{a=Math.min(a,q[1]);z=Math.max(z,q[1])});x.fillStyle=col;
    for(let y=Math.ceil(a-.5);y<=Math.floor(z-.5);y++){const yy=y+.5,xs=[];
      for(let i=0;i<pts.length;i++){const s=pts[i],e=pts[(i+1)%pts.length];if((s[1]<=yy&&e[1]>yy)||(e[1]<=yy&&s[1]>yy))xs.push(s[0]+(yy-s[1])/(e[1]-s[1])*(e[0]-s[0]))}
      xs.sort((m,n)=>m-n);for(let k=0;k+1<xs.length;k+=2){const x0=Math.round(xs[k]),x1=Math.round(xs[k+1]);if(x1>x0)x.fillRect(x0,y,x1-x0,1)}}}
  let sd=5;const rnd=()=>{sd=(sd*16807)%2147483647;return sd/2147483647};
  function line(x,x0,y0,x1,y1,col){x0|=0;y0|=0;x1|=0;y1|=0;x.fillStyle=col;const dx=Math.abs(x1-x0),dy=-Math.abs(y1-y0),sx=x0<x1?1:-1,sy=y0<y1?1:-1;let e=dx+dy,e2;for(;;){x.fillRect(x0,y0,1,1);if(x0===x1&&y0===y1)break;e2=2*e;if(e2>=dy){e+=dy;x0+=sx}if(e2<=dx){e+=dx;y0+=sy}}}
  function circ(x,cx,cy,r,col){x.fillStyle=col;for(let dy=-r;dy<=r;dy++)for(let dx=-r;dx<=r;dx++)if(dx*dx+dy*dy<=r*r+r*.6)x.fillRect(cx+dx,cy+dy,1,1)}

  {
    const RY=19,OX=190,OY=46;const pr0=(X,Y,Z)=>[OX+(X-Y)*8,OY+(X+Y)*4-Z];let pr=pr0;const shift=(dx,dy)=>{pr=(X,Y,Z)=>pr0(X+dx,Y+dy,Z)};
    const poly=(col,pts)=>P(x,col,pts);
    const wallR=(X0,X1,Z0,Z1,col)=>poly(col,[pr(X0,0,Z0),pr(X1,0,Z0),pr(X1,0,Z1),pr(X0,0,Z1)]);
    const wallL=(Y0,Y1,Z0,Z1,col)=>poly(col,[pr(0,Y0,Z0),pr(0,Y1,Z0),pr(0,Y1,Z1),pr(0,Y0,Z1)]);
    const box=(X,Y,Z,w,d,h,t,l,r)=>{
      poly(t,[pr(X,Y,Z+h),pr(X+w,Y,Z+h),pr(X+w,Y+d,Z+h),pr(X,Y+d,Z+h)]);
      poly(l,[pr(X,Y+d,Z),pr(X+w,Y+d,Z),pr(X+w,Y+d,Z+h),pr(X,Y+d,Z+h)]);
      poly(r,[pr(X+w,Y,Z),pr(X+w,Y+d,Z),pr(X+w,Y+d,Z+h),pr(X+w,Y,Z+h)]);
    };
    x.fillStyle='#120d0a';x.fillRect(0,0,320,190);
    wallL(0,RY,0,44,'#5c4d3f');wallR(0,12,0,44,'#7a6a58');
    wallL(0,RY,0,3,'#2e241d');wallR(0,12,0,3,'#3a2e25');
    poly('#9a8a76',[pr(0,0,44),pr(0,RY,44),pr(-.6,RY,44),pr(-.6,0,44)]);
    poly('#a99985',[pr(0,0,44),pr(12,0,44),pr(12,-.6,44),pr(0,-.6,44)]);
    for(let X=0;X<12;X++)for(let Y=0;Y<RY;Y++){const rug=X>=3&&X<9&&Y>=3&&Y<9;const rim=rug&&(X===3||X===8||Y===3||Y===8);
      const col=rim?'#7a4a3a':rug?(((X+Y)%2)?'#4d2a2c':'#46262a'):(((X+Y)%2)?'#3b302a':'#342a24');
      poly(col,[pr(X,Y,0),pr(X+1,Y,0),pr(X+1,Y+1,0),pr(X,Y+1,0)])}
    // стена справа: штора, плющ, REC
    wallR(2.5,9.5,6,40,'#1c1512');for(let X=2.5;X<9.5;X+=.5){wallR(X,X+.2,6,40,'#120d0b');wallR(X+.3,X+.4,6,40,'#2b201a')}
    wallR(2.3,9.7,40,42,'#0d0907');
    // тени
    poly('#1e1713',[pr(3.2,.4,0),pr(9.4,.4,0),pr(9.4,2.6,0),pr(3.2,2.6,0)]);
    poly('#1e1713',[pr(4.4,4,0),pr(6.8,4,0),pr(6.8,6.4,0),pr(4.4,6.4,0)]);poly('#1e1713',[pr(6.9,4.4,0),pr(9.3,4.4,0),pr(9.3,6.8,0),pr(6.9,6.8,0)]);
    // стол
    [[2.7,.4],[8.9,.4],[2.7,1.8],[8.9,1.8]].forEach(([X,Y])=>box(X,Y,0,.3,.3,12,'#aab1b8','#848b92','#5d646b'));
    box(2.5,.2,12,7,2,3,'#a87a48','#8a6238','#6b4a2a');
    // монитор с заставкой «ГАРАЖ»
    tag('screen');
    const mon=(X0,w,kind)=>{const Y=.75;box(X0+w/2-.4,Y+.05,15,.8,.4,2,'#2a2a2a','#1c1c1c','#111');
      box(X0+w/2-.12,Y+.1,15,.24,.3,5,'#333','#222','#111');
      box(X0,Y,18,w,.25,13,'#222','#0a0a0c','#111');
      const t=pr(X0,Y+.25,31),W=Math.round(w*8)-2;
      x.fillStyle='#3a2414';for(let u=1;u<=W;u++)x.fillRect(t[0]+u,t[1]+1+Math.floor(u*.5),1,10);
      const f=(u,v,col)=>{x.fillStyle=col;x.fillRect(t[0]+u,t[1]+1+v+Math.floor(u*.5),1,1)};
      for(let n=0;n<5;n++){const m=BIG['ГАРАЖ'[n]],u0=1+n*6,off=Math.floor((u0+2)*.5);for(let j=0;j<5;j++)for(let i=0;i<5;i++)if(m[j][i]==='1'){x.fillStyle='#e8dcbf';x.fillRect(t[0]+u0+i,t[1]+1+2+j+off,1,1)}}
      for(let k=0;k<4;k++){const u0=7+k*4,off=Math.floor((u0+1)*.5);x.fillStyle='#9c8c6e';x.fillRect(t[0]+u0,t[1]+1+8+off,3,1)}};
    mon(4.3,4.0,'logo');
    tag('speakers');
    [3.0,8.5].forEach(X=>{box(X,.5,15,.9,.9,11,'#222','#161616','#0d0d0d');
      const t=pr(X,1.4,26);const g=(u,v,col)=>{x.fillStyle=col;x.fillRect(t[0]+u,t[1]+v+Math.floor(u*.5),1,1)};
      for(let v=0;v<11;v++)for(let u=0;u<7;u++){const dx=u-3.5,dy=v-6.5;const d=dx*dx+dy*dy;if(d<=10)g(u,v,d<=2?'#3d3d3d':d<=6?'#262626':'#0b0b0b')}
      for(let u=1;u<6;u++)g(u,1,'#2b2b2b')});
    tag(null);
    // кресла
    [[4.4,4],[6.9,4.4]].forEach(([X,Y])=>{
      box(X+.9,Y+.9,0,.3,.3,8,'#4a4f52','#3a3f42','#2a2f32');
      box(X,Y,8,2,2,3,'#3a4658','#2f3948','#242c38');
      box(X+.1,Y+1.6,11,1.8,.4,15,'#cfd3d5','#8f979b','#6a7378');
      box(X+.5,Y+1.6,26,1,.4,4,'#e4e7e8','#cfd3d5','#9aa0a3');
      const t=pr(X+.1,Y+2,26);for(let j=0;j<12;j+=2)for(let u=1+(j/2%2);u<14;u+=2){x.fillStyle='#6a7378';x.fillRect(t[0]+u,t[1]+1+j+Math.floor(u*.5),1,1)}});
    // белая MIDI-клавиатура на X-стойке
    poly('#1e1713',[pr(10.1,5,0),pr(12,5,0),pr(12,9,0),pr(10.1,9,0)]);
    tag('keys');
    [5.8,8.2].forEach(Y=>{[[10.6,11.4],[11.4,10.6]].forEach(([a,b])=>{const p=pr(a,Y,0),q=pr(b,Y,15);line(x,p[0],p[1],q[0],q[1],'#1c1c20');line(x,p[0]+1,p[1],q[0]+1,q[1],'#2e2e34')});
      const f=pr(11,Y,0);x.fillStyle='#111';x.fillRect(f[0]-6,f[1],13,1)});
    box(10.45,5.2,15,1.4,3.6,1.6,'#f3efe6','#d9d3c6','#b8b2a2');
    box(10.45,5.2,16.6,.5,3.6,.4,'#c9c3b4','#b3ad9e','#9a9486');
    for(let k=0;k<9;k++){const t=pr(10.8,5.45+k*.38,16.8);x.fillStyle='#222';x.fillRect(t[0],t[1],2,1)}
    for(let k=0;k<4;k++){const t=pr(10.5,5.4+k*.5,16.9);x.fillStyle=k===3?'#c0392b':'#444';x.fillRect(t[0],t[1],2,1)}
    tag(null);
    // декор на стенах
    tag('address');
    wallL(2.2,3.7,24,40,'#d9d2c3');wallL(2.7,3.2,32,35,'#d33a2f');wallL(2.9,3.0,27,31,'#d33a2f'); // плакат с булавкой
    tag('contacts');
    wallL(4.4,6.1,26,38,'#2b9bd8');wallL(4.7,5.8,31,33,'#fff');wallL(5.0,5.5,34,36,'#fff');     // синий знак «самолёт»
    tag('prices');
    wallL(11.2,13.8,14,38,'#e4d6a8');wallL(11.2,13.8,32,38,'#b3312b');for(let z=16;z<30;z+=3)wallL(11.6,13.4,z,z+1,'#4b4030'); // прайс-панель
    tag(null);
    wallL(14.6,17.0,12,38,'#3a2320');wallL(14.8,16.8,14,36,'#4a2e2a');                              // тёмная акустическая панель
    tag('rec');wallR(7.8,9.4,33,38,'#17100d');blink(true);wallR(8,8.4,34.5,36.5,'#ff2d2d');blink(false);wallR(8.7,9.2,34.8,36,'#6b5a48'); // табло REC
    tag(null);
    for(let i=0;i<26;i++){const X=0.15+rnd()*0.8,Z=6+rnd()*34;wallR(X,X+.35,Z,Z+3,['#2f5a2e','#3f7a3a','#26482a'][i%3])}   // плющ слева от шторы
    for(let i=0;i<26;i++){const X=9.6+rnd()*1.0,Z=8+rnd()*32;wallR(X,X+.35,Z,Z+3,['#2f5a2e','#3f7a3a','#26482a'][i%3])}   // плющ справа от шторы
    // электрогитара Stratocaster — рисованный спрайт на подставке
    tag('guitar');
    {const base=pr(.55,8.8,0);
     const G=[
      '....kkk.....',
      '....kkg.....',
      '....kkg.....',
      '....kkg.....',
      '....kkg.....',
      '....kk......',
      '....nn......',
      '....ff......',
      '....nn......',
      '....nw......',
      '....ff......',
      '....nn......',
      '....nw......',
      '....ff......',
      '..k.nn......',
      '.kk.nn...k..',
      '.kh.ff..kk..',
      '.khkwwwkk...',
      '.hkwwbwwk...',
      '..hkwbbwk...',
      '..hkwwwwk...',
      '.hkkwbbwkk..',
      'khkkwwwwkkk.',
      'khkkwbbbwkk.',
      'khkkkwwwkkk.',
      'khkkkssskkk.',
      '.hkkkkkkkk..',
      '..kkkkkkk...',
      '....kkk.....'];
     const C={k:'#151517',K:'#070708',h:'#34343a',w:'#eeebe4',b:'#26262a',g:'#a0a0a8',n:'#2b2b30',f:'#6a6a72',s:'#c4c7cc'};
     const ox=base[0]-5,oy=base[1]-G.length-2;
     // тень и подставка
     x.fillStyle='rgba(0,0,0,.35)';x.fillRect(ox,base[1]-2,12,2);x.fillRect(ox+2,base[1]-3,8,1);
     x.fillStyle='#1c1c20';x.fillRect(ox+1,base[1]-3,9,1);x.fillRect(ox+1,base[1]-6,1,3);x.fillRect(ox+8,base[1]-6,1,3);
     // толщина корпуса (смещение вправо)
     G.forEach((r,j)=>[...r].forEach((ch,i)=>{if(ch!=='.'&&j>12){x.fillStyle='#050506';x.fillRect(ox+i+1,oy+j,1,1)}}));
     G.forEach((r,j)=>[...r].forEach((ch,i)=>{if(ch!=='.'){x.fillStyle=C[ch];x.fillRect(ox+i,oy+j,1,1)}}));
    }
    tag('mic');
    // стойка с микрофоном
    {const bx=1.7,by=6.6;const f=pr(bx,by,0);const px=f[0],py=f[1];
     const R=(X,Y,w,h,c)=>{x.fillStyle=c;x.fillRect(X,Y,w,h)};
     poly('rgba(0,0,0,.3)',[pr(bx-.8,by-.3,0),pr(bx+.5,by-.8,0),pr(bx+.9,by+.6,0),pr(bx-.4,by+.9,0)]);
     const hub=[px,py-4];
     [[-8,2],[8,2],[1,6]].forEach(([dx,dy])=>{const ex=px+dx,ey=py+dy;
       line(x,hub[0],hub[1],ex,ey-1,'#1a1a1e');line(x,hub[0]+1,hub[1],ex+1,ey-1,'#3b3b42');R(ex-1,ey-1,2,2,'#0b0b0d')});
     R(px-2,hub[1]-1,4,3,'#2e2e34');R(px-2,hub[1]-1,4,1,'#6a6a72');
     R(px-1,py-20,2,16,'#2b2b31');R(px-1,py-20,1,16,'#4b4b54');
     R(px-2,py-13,4,2,'#8d8d96');R(px-2,py-13,4,1,'#c9c9d2');
     R(px,py-30,1,10,'#5a5a64');
     R(px-2,py-31,5,2,'#3a3a42');R(px-2,py-31,5,1,'#7a7a84');
     line(x,px+2,py-30,px+10,py-34,'#2a2a31');line(x,px+2,py-31,px+10,py-35,'#4b4b54');
     const mx=px+10,my=py-27;
     // амортизатор
     x.fillStyle='#202026';for(let a=0;a<28;a++){const t=a/28*6.283;x.fillRect(Math.round(mx+4.5*Math.cos(t)),Math.round(my+6*Math.sin(t)),1,1)}
     // микрофон: тёмный корпус, серая сетка
     R(mx-2,my-4,5,10,'#16161a');R(mx-2,my-4,1,10,'#2c2c33');R(mx+2,my-4,1,10,'#0a0a0c');
     R(mx-2,my-5,5,3,'#6f6f78');R(mx-2,my-5,5,1,'#a0a0aa');R(mx-1,my-4,1,1,'#2a2a30');R(mx+1,my-3,1,1,'#2a2a30');
     blink(true);R(mx+1,my+3,1,1,'#ff2d2d');blink(false);R(mx-1,my+6,3,2,'#44444c');
     line(x,mx,my+8,px+2,py-14,'#0e0e10');
     // поп-фильтр
     const fx=mx+9,fy=my-1;
     x.fillStyle='rgba(30,30,36,.55)';for(let a=-5;a<=5;a++)for(let b=-6;b<=6;b++)if(a*a/25+b*b/36<=1&&((a+b)&1)===0)x.fillRect(fx+a,fy+b,1,1);
     x.fillStyle='#0d0d10';for(let a=0;a<36;a++){const t=a/36*6.283;x.fillRect(Math.round(fx+5*Math.cos(t)),Math.round(fy+6*Math.sin(t)),1,1)}
     line(x,mx+3,my-2,fx-5,fy,'#2b2b31');
    }
    tag(null);
    shift(0,4.1);
    // деревянный стеллаж-этажерка (реечные полки, высокие стойки, связи)
    {const X0=8.7,X1=11.9,Y0=8.35,Y1=9.45,TOP=36,Wd=['#a87a48','#8a6238','#6b4a2a'],Pd=['#8a5c34','#734c2a','#5a3a1f'];
     poly('#1e1713',[pr(X0-.2,Y0-.2,0),pr(X1+.3,Y0-.2,0),pr(X1+.3,Y1+.4,0),pr(X0-.2,Y1+.4,0)]);
     tag('shelf');
     const post=(X,Y)=>box(X,Y,0,.32,.32,TOP,Pd[0],Pd[1],Pd[2]);
     post(X0,Y0);post(X1-.32,Y0);
     // задняя диагональная связь
     {const a=pr(X0+.3,Y0,4),b=pr(X1-.3,Y0,TOP-4);line(x,a[0],a[1],b[0],b[1],'#5a3a1f')}
     const levels=[3,13,23,33];
     const shelfAt=z=>{for(let k=0;k<3;k++){box(X0+.05,Y0+.05+k*.36,z,X1-X0-.1,.3,1,Wd[0],Wd[1],Wd[2])}};
     const B=(X,Y,z,w,d,h,c)=>box(X,Y,z,w,d,h,c[0],c[1],c[2]);
     const white=['#efece4','#dad7cd','#b5b2a8'],blk=['#2a2a2a','#1d1d1d','#111'],olive=['#7a8468','#636c53','#4c5440'],red=['#c8403a','#a3322d','#7a2420'];
     levels.forEach((z,k)=>{shelfAt(z);const zz=z+1;
       if(k===0){ // книги стоя + красная коробка
         ['#7a2d2a','#c9b46a','#e6e3dc','#2a3a5a','#d8d2c4','#5a4630'].forEach((c,i)=>B(X0+.25+i*.22,Y0+.25,zz,.18,.75,7+(i%3),[c,c,c]));
         B(X0+1.9,Y0+.3,zz,1.0,.6,3,red);}
       if(k===1){ // коробка Audio-Technica и кружки
         B(X0+.3,Y0+.2,zz,1.0,.8,8,white);{const q=pr(X0+.55,Y0+1.0,zz+6);x.fillStyle='#222';x.fillRect(q[0],q[1],2,4)}
         [1.7,2.2,2.7].forEach(X=>{B(X0+X,Y0+.45,zz,.35,.35,3,olive);const q=pr(X0+X+.35,Y0+.62,zz+2);x.fillStyle='#4c5440';x.fillRect(q[0],q[1]-1,1,2)});}
       if(k===2){ // коробка Mac и чёрный прибор
         B(X0+.3,Y0+.25,zz,.9,.7,5,white);{const q=pr(X0+.7,Y0+.95,zz+3);x.fillStyle='#777';x.fillRect(q[0],q[1],2,1)}
         B(X0+1.6,Y0+.35,zz,.9,.5,2,blk);B(X0+2.6,Y0+.4,zz,.25,.25,4,['#d8d2c4','#bdb7a8','#9a9486']);}
       if(k===3){ // горшок со змеиным растением
         B(X0+1.4,Y0+.35,zz,.55,.55,3,['#e8e2d4','#cfc9bb','#aaa496']);
         const c0=pr(X0+1.67,Y0+.62,zz+3);[[0,-9],[-2,-7],[2,-8],[-1,-6],[3,-6],[-3,-5]].forEach(([dx,h],i)=>{x.fillStyle=i%2?'#3f7a3a':'#5a9a4a';for(let j=0;j<-h;j++){x.fillRect(c0[0]+dx+Math.round(dx*j/12),c0[1]-j,j<-h-2?2:1,1)}x.fillStyle='#c9c26a';x.fillRect(c0[0]+dx,c0[1]-1,1,1)});}
     });
     post(X0,Y1-.32);post(X1-.32,Y1-.32);
     // боковая X-связь на торце
     {const a=pr(X1,Y0+.1,3),b=pr(X1,Y1-.1,15),c2=pr(X1,Y1-.1,3),d=pr(X1,Y0+.1,15);line(x,a[0],a[1],b[0],b[1],'#5a3a1f');line(x,c2[0],c2[1],d[0],d[1],'#5a3a1f')}
    }
    tag(null);
    shift(.4,2.6);
    // оливковое кресло-«бочка»: скруглённая спинка-обод, подушка, деревянная рама
    {const cx=7.2,cy=13.45,R=1.25,r=.78,Z0=6,N=28;
     const H=t=>Z0+6.5+5.5*Math.max(0,-Math.cos(t)); // спинка выше сзади, ниже у подлокотников
     const P_=(rr,t,z)=>pr(cx+rr*Math.cos(t),cy+rr*Math.sin(t),z);
     poly('rgba(0,0,0,.35)',[pr(cx-1.4,cy-1.3,0),pr(cx+1.4,cy-1.3,0),pr(cx+1.4,cy+1.4,0),pr(cx-1.4,cy+1.4,0)]);
     // деревянные ножки с наклоном
     [[.8,.75],[-.8,.75],[.8,-.75],[-.8,-.75]].forEach(([dx,dy])=>{const a=pr(cx+dx*.75,cy+dy*.75,Z0),b=pr(cx+dx*1.05,cy+dy*1.05,0);
       line(x,a[0],a[1],b[0],b[1],'#946c3a');line(x,a[0]+1,a[1],b[0]+1,b[1],'#b58850')});
     // нижняя рама/царга
     {const pts=[];for(let i=0;i<=24;i++){const t=i/24*6.283;pts.push(pr(cx+1.05*Math.cos(t),cy+1.05*Math.sin(t),Z0))}
      for(let i=24;i>=0;i--){const t=i/24*6.283;pts.push(pr(cx+1.05*Math.cos(t),cy+1.05*Math.sin(t),Z0+1))}}
     const segs=[];for(let i=0;i<N;i++){const t0=Math.PI/2+i/N*Math.PI,t1=Math.PI/2+(i+1)/N*Math.PI,tm=(t0+t1)/2;segs.push({t0,t1,d:Math.cos(tm)+Math.sin(tm)})}
     segs.sort((a,b)=>a.d-b.d);
     const drawSeg=g=>{const{t0,t1}=g,h0=H(t0),h1=H(t1);
       // внутренняя поверхность
       poly('#3f4430',[P_(r,t0,Z0),P_(r,t1,Z0),P_(r,t1,h1),P_(r,t0,h0)]);
       // внешняя
       const nx=Math.cos((t0+t1)/2),ny=Math.sin((t0+t1)/2);const lit=nx*.6-ny*.4;
       const oc=lit>.2?'#5e6545':lit>-.3?'#4f5539':'#40452f';
       poly(oc,[P_(R,t0,Z0),P_(R,t1,Z0),P_(R,t1,h1),P_(R,t0,h0)]);
       // верх обода (скруглённый кант)
       poly('#6f7652',[P_(R,t0,h0),P_(R,t1,h1),P_(r,t1,h1),P_(r,t0,h0)]);
       poly('#7f8760',[P_((R+r)/2,t0,h0+.6),P_((R+r)/2+.12,t1,h1+.6),P_((R+r)/2-.05,t1,h1),P_((R+r)/2-.17,t0,h0)])};
     // сначала дальние сегменты, затем подушка, затем ближние
     segs.filter(g=>g.d<=0).forEach(drawSeg);
     // подушка сиденья (скруглённый цилиндр)
     {const zt=Z0+3.4,rs=1.0;const side=[],top=[];
      for(let i=0;i<=20;i++){const t=-Math.PI/4+i/20*Math.PI;side.push(pr(cx+.15+rs*Math.cos(t),cy+rs*Math.sin(t),Z0))}
      for(let i=20;i>=0;i--){const t=-Math.PI/4+i/20*Math.PI;side.push(pr(cx+.15+rs*Math.cos(t),cy+rs*Math.sin(t),zt))}
      poly('#565c40',side);
      for(let i=0;i<32;i++){const t=i/32*6.283;top.push(pr(cx+.15+rs*Math.cos(t),cy+rs*Math.sin(t),zt))}
      poly('#737a55',top);
      const c0=pr(cx+.15,cy,zt);x.fillStyle='#858d66';x.fillRect(c0[0]-3,c0[1]-1,6,1);
      for(let i=0;i<10;i++){const a=(rnd()-.5)*12,b=(rnd()-.5)*6;x.fillStyle='rgba(70,76,50,.25)';x.fillRect(Math.round(c0[0]+a),Math.round(c0[1]+b),1,1)}}
     segs.filter(g=>g.d>0).forEach(drawSeg);
     // деревянные накладки рамы на торцах подлокотников (как на фото)
     [Math.PI/2+.08,3*Math.PI/2-.08].forEach(t=>{const a=P_(R+.02,t,Z0-.5),b=P_(R+.02,t,H(t)-1);line(x,a[0],a[1],b[0],b[1],'#a87a48');line(x,a[0]+1,a[1],b[0]+1,b[1],'#c79a62')});
     // фактура букле на ободе
     for(let i=0;i<22;i++){const t=Math.PI/2+rnd()*Math.PI,rr=r+rnd()*(R-r),q=P_(rr,t,H(t));x.fillStyle='rgba(60,66,42,.25)';x.fillRect(Math.round(q[0]),Math.round(q[1]),1,1)}
    }
    shift(0,2);
    // бежевый диван у края (спинка к зрителю)
    poly('#1e1713',[pr(7.6,15.2,0),pr(12,15.2,0),pr(12,17,0),pr(7.6,17,0)]);
    const B=['#9a7656','#83634a','#6b4f3a'],Bd=['#8c6a4d','#755841','#5e4533'];
    box(8,15.4,0,4,1.6,6,B[0],B[1],B[2]);            // основание/сиденье
    box(8,16.3,6,4,.7,10,Bd[0],Bd[1],Bd[2]);         // спинка
    shift(0,2.6);
    // кофейный столик с лампой
    poly('#1e1713',[pr(9.9,11.9,0),pr(11.6,11.9,0),pr(11.6,13.6,0),pr(9.9,13.6,0)]);
    [[10.1,12.1],[11.0,12.1],[10.1,13.0],[11.0,13.0]].forEach(([X,Y])=>box(X,Y,0,.3,.3,8,'#6b4a2a','#5e4226','#4a331c'));
    box(10.0,12.0,8,1.5,1.5,1.5,'#a87a48','#8a6238','#6b4a2a');
    box(10.45,12.45,9.5,.6,.6,8,'#fff6e2','#ffe2b0','#e8c898');
    glow(true);
    {const q=pr(10.75,12.75,15);for(let a=-12;a<=12;a++)for(let b=-10;b<=10;b++){const d=Math.hypot(a,b);if(d<12&&d>5&&((a+b)&1)===0&&d<12*(.9-((((a&1)+((b&1)<<1))+.5)/4)*.5)){x.fillStyle='rgba(255,190,100,.25)';x.fillRect(q[0]+a,q[1]+b,1,1)}}}
    glow(false);
  }

  // Обрезаем пустые поля вокруг комнаты.
  const img = real.getImageData(0, 0, W, H).data;
  let bx0 = W, by0 = H, bx1 = 0, by1 = 0;
  for (let yy = 0; yy < H; yy++) for (let xx = 0; xx < W; xx++) {
    const i = (yy * W + xx) * 4;
    if (img[i] !== 0x12 || img[i + 1] !== 0x0d || img[i + 2] !== 0x0a) {
      if (xx < bx0) bx0 = xx; if (xx > bx1) bx1 = xx; if (yy < by0) by0 = yy; if (yy > by1) by1 = yy;
    }
  }
  bx0 = Math.max(0, bx0 - PAD); by0 = Math.max(0, by0 - PAD); bx1 = Math.min(W - 1, bx1 + PAD); by1 = Math.min(H - 1, by1 + PAD);
  const cw = bx1 - bx0 + 1, ch = by1 - by0 + 1;
  const mk = (w, h) => { const k = document.createElement('canvas'); k.width = w; k.height = h; return k; };
  const scene = mk(cw, ch); scene.getContext('2d').drawImage(c, -bx0, -by0);
  const map = mk(cw, ch); const mctx = map.getContext('2d'); const md = mctx.createImageData(cw, ch);
  const objects = {};
  for (let yy = 0; yy < ch; yy++) for (let xx = 0; xx < cw; xx++) {
    const s = (yy + by0) * W + xx + bx0, d = (yy * cw + xx) * 4, id = idMap[s];
    md.data[d] = id * 20; md.data[d + 1] = blinkMap[s] ? 255 : 0; md.data[d + 2] = glowMap[s] ? 255 : 0; md.data[d + 3] = 255;
    if (id) {
      const o = objects[IDS[id - 1]] || (objects[IDS[id - 1]] = {x0: 1e9, y0: 1e9, x1: -1, y1: -1});
      if (xx < o.x0) o.x0 = xx; if (xx > o.x1) o.x1 = xx; if (yy < o.y0) o.y0 = yy; if (yy > o.y1) o.y1 = yy;
    }
  }
  mctx.putImageData(md, 0, 0);
  const og = mk(1200, 630); const octx = og.getContext('2d');
  octx.fillStyle = '#120d0a'; octx.fillRect(0, 0, 1200, 630); octx.imageSmoothingEnabled = false;
  const k = Math.floor(Math.min(1200 / cw, 630 / ch));
  octx.drawImage(scene, Math.round((1200 - cw * k) / 2), Math.round((630 - ch * k) / 2), cw * k, ch * k);
  // Иконка вкладки: экран студии с буквой «Г».
  const fav = mk(64, 64); const fctx = fav.getContext('2d');
  ['1111111111111111', '1222222222222221', '1222222222222221', '1223333333332221', '1223333333332221', '1223322222222221',
   '1223322222222221', '1223322222222221', '1223322222222221', '1223322222222221', '1223322222222221', '1222222222222221',
   '1222222222222221', '1111111111111111', '0000001111000000', '0000111111110000'].forEach((row, j) => [...row].forEach((ch, i) => {
    if (ch === '0') return;
    fctx.fillStyle = {1: '#0a0a0c', 2: '#3a2414', 3: '#e8dcbf'}[ch]; fctx.fillRect(i * 4, j * 4, 4, 4);
  }));
  const boxes = {};
  for (const [name, o] of Object.entries(objects)) boxes[name] = [o.x0, o.y0, o.x1 - o.x0 + 1, o.y1 - o.y0 + 1];
  return {
    scene: scene.toDataURL('image/png'), map: map.toDataURL('image/png'), og: og.toDataURL('image/png'), favicon: fav.toDataURL('image/png'),
    meta: {width: cw, height: ch, ids: IDS, boxes},
  };
}

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const out = await page.evaluate(`(${drawScene.toString()})(${JSON.stringify(IDS)})`);
  await browser.close();
  const save = (name, dataUrl) => fs.writeFileSync(path.join(OUT, name), Buffer.from(dataUrl.split(',')[1], 'base64'));
  save('scene.png', out.scene); save('scene-map.png', out.map); save('og.png', out.og); save('favicon.png', out.favicon);
  fs.writeFileSync(path.join(OUT, 'scene.json'), JSON.stringify(out.meta) + '\n');
  console.log(out.meta);
})();
