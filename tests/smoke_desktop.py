from pathlib import Path
import sys,json,os,time
from unittest.mock import patch
import argparse,shutil,tempfile
parser=argparse.ArgumentParser(description='Exercise UI using a complete installed runtime in an isolated temporary folder.')
parser.add_argument('--runtime',required=True,type=Path)
parser.add_argument('--screenshots',type=Path)
args=parser.parse_args()
work=tempfile.TemporaryDirectory(prefix='maple_ui_smoke_');runtime=Path(work.name)
# Never read or copy settings, credentials, recorded sessions or model caches.
for source in args.runtime.glob('*.py'):shutil.copy2(source,runtime/source.name)
for name in ('verified_items.json','buff_wealth.png','buff_union_wealth.png','buff_union_luck.png'):
 shutil.copy2(args.runtime/name,runtime/name)
(runtime/'ocr_aliases.json').write_text('{}')
sys.path.insert(0,str(runtime))
config={'setup_guide_v1':True,'normal_window_migrated':True,'topmost':False,'cumulative_elapsed_seconds':7200,'cumulative_items':{},'revenue_goal':300000000,'skill_timers':[{'id':'test-skill','name':'에르다 샤워','seconds':60,'alert':5,'sound':False}], 'price_books':{'스카니아':{'fee_percent':'5','items':{'코어 젬스톤':{'unit_price':800000},'솔 에르다 조각':{'unit_price':7000000},'순록의 우유':{'unit_price':1000}}}}}
(runtime/'settings.json').write_text(json.dumps(config,ensure_ascii=False))
import api_key_store
with patch.object(api_key_store.KeyStore,'load',return_value=''):
 import maple_loot_counter as app
 owner=app.MapleLootCounter()
errors=[];owner.report_callback_exception=lambda *args:errors.append(str(args[1]))
owner.items.update({'코어 젬스톤':23,'솔 에르다 조각':18,'순록의 우유':240,'황혼의 이슬':110})
owner.refresh_table()
owner._wallet.start('1000000000',owner._daily.combined()['net'])
owner._wallet.transaction('3000000','재획비','출금',True)
owner._wallet.finish('1057000000',owner._daily.combined()['net'])
owner._wallet_refresh();owner.refresh_table();owner.update_clock()
from PIL import ImageGrab
out=args.screenshots
if out:out.mkdir(parents=True,exist_ok=True)
for size in ('1280x900','980x700'):
 owner.geometry(size+'+0+0')
 for page in ('home','wallet','skills','records','settings'):
  owner.show_page(page);owner.update_idletasks();owner.update()
  if out:
   image=ImageGrab.grab(xdisplay=os.environ.get('DISPLAY'))
   image.crop((0,0,owner.winfo_width(),owner.winfo_height())).save(out/f'{page}-{size}.png')
  if page=='home':assert owner.item_tree.winfo_height()>=190
  print(page,size,'shown',owner.workspace_pages[page].winfo_ismapped(),'wallet',owner._wallet_window.winfo_class(),flush=True)
owner.workspace_focus_button.invoke();owner.update();assert owner._workspace_page=='home'
owner.workspace_focus_button.invoke();owner.update()
assert not owner._meso.data['enabled']
print('callback errors:',errors)
# Callbacks remain available after all page switches.
for callback in ('edit_skill_timers','show_daily_history','open_hunt_records','export_csv','edit_prices','select_region','request_wallet_start','request_wallet_end','resume_wallet'):
 assert callable(getattr(owner,callback)),callback
skill=owner.edit_skill_timers();owner.update();assert skill.winfo_exists();skill.destroy()
history_before=json.dumps(owner._wallet.data,sort_keys=True)
for page in owner.workspace_pages:owner.show_page(page);owner.update()
assert json.dumps(owner._wallet.data,sort_keys=True)==history_before
owner.destroy()
if errors:raise SystemExit(1)
