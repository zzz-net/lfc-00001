import requests
import sys

sys.stdout.reconfigure(encoding='utf-8')

BASE = 'http://localhost:8000'

users = requests.get(f'{BASE}/api/reimbursements/users').json()
print(f'用户数量: {len(users)}')

finance = None
for u in users:
    if u['role'] == 'finance':
        finance = u
        break

if finance:
    fid = finance['id']
    print(f'财务用户ID: {fid}')
    
    batches = requests.get(f'{BASE}/api/import/batches?user_id={fid}&limit=10').json()
    print(f'批次数量: {len(batches)}')
    for b in batches[:3]:
        print(f'  批次{b["id"]}: {b["file_name"]} - {b["status"]} (成功{b["success_count"]}/失败{b["failed_count"]}/跳过{b["skipped_count"]})')
    
    reimbs = requests.get(f'{BASE}/api/reimbursements?user_id={fid}&limit=20').json()
    print(f'报销单数量: {len(reimbs)}')
    
    if batches:
        bid = batches[0]['id']
        logs = requests.get(f'{BASE}/api/audit/batch/{bid}?user_id={fid}').json()
        print(f'批次{bid}的审计日志数量: {len(logs)}')
    
    if batches and len(batches) > 0 and len(reimbs) > 0:
        print()
        print('[PASS] 重启后数据持久化验证通过！')
    else:
        print()
        print('[FAIL] 数据丢失！')
else:
    print('未找到财务用户')
