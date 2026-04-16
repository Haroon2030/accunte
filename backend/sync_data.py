"""
سكريبت نقل البيانات من قاعدة البيانات المحلية إلى الخادم
"""
import sqlite3
import requests
import json

# إعدادات الخادم
SERVER_URL = "http://72.61.107.230:8096/api/v1"

def get_local_data():
    """استخراج البيانات من قاعدة البيانات المحلية"""
    conn = sqlite3.connect('db.sqlite3')
    conn.row_factory = sqlite3.Row
    
    data = {}
    
    # مراكز التكلفة
    cursor = conn.execute('SELECT * FROM cost_centers_costcenter')
    data['cost_centers'] = [dict(row) for row in cursor.fetchall()]
    print(f"✓ مراكز التكلفة: {len(data['cost_centers'])} سجل")
    
    # الفروع
    cursor = conn.execute('SELECT * FROM branches_branch')
    data['branches'] = [dict(row) for row in cursor.fetchall()]
    print(f"✓ الفروع: {len(data['branches'])} سجل")
    
    # البنوك
    cursor = conn.execute('SELECT * FROM banks_bank')
    data['banks'] = [dict(row) for row in cursor.fetchall()]
    print(f"✓ البنوك: {len(data['banks'])} سجل")
    
    # الموردين
    cursor = conn.execute('SELECT * FROM suppliers_supplier')
    data['suppliers'] = [dict(row) for row in cursor.fetchall()]
    print(f"✓ الموردين: {len(data['suppliers'])} سجل")
    
    conn.close()
    return data

def upload_cost_centers(cost_centers):
    """رفع مراكز التكلفة"""
    print("\n📤 رفع مراكز التكلفة...")
    success = 0
    errors = 0
    
    for cc in cost_centers:
        payload = {
            "name": cc['name'],
            "code": cc['code'],
            "description": cc.get('description', ''),
            "is_active": bool(cc.get('is_active', 1))
        }
        
        try:
            response = requests.post(f"{SERVER_URL}/cost-centers/", json=payload)
            if response.status_code in [200, 201]:
                success += 1
            else:
                errors += 1
                if errors <= 3:
                    print(f"  خطأ في {cc['name']}: {response.text[:100]}")
        except Exception as e:
            errors += 1
            if errors <= 3:
                print(f"  استثناء: {e}")
    
    print(f"  ✓ نجح: {success} | ✗ فشل: {errors}")

def upload_branches(branches):
    """رفع الفروع"""
    print("\n📤 رفع الفروع...")
    success = 0
    errors = 0
    
    for branch in branches:
        payload = {
            "name": branch['name'],
            "code": branch['code'],
            "address": branch.get('address', ''),
            "phone": branch.get('phone', ''),
            "is_active": bool(branch.get('is_active', 1)),
            "cost_center": branch.get('cost_center_id')
        }
        
        try:
            response = requests.post(f"{SERVER_URL}/branches/", json=payload)
            if response.status_code in [200, 201]:
                success += 1
            else:
                errors += 1
                if errors <= 3:
                    print(f"  خطأ في {branch['name']}: {response.text[:100]}")
        except Exception as e:
            errors += 1
            if errors <= 3:
                print(f"  استثناء: {e}")
    
    print(f"  ✓ نجح: {success} | ✗ فشل: {errors}")

def upload_banks(banks):
    """رفع البنوك"""
    print("\n📤 رفع البنوك...")
    success = 0
    errors = 0
    
    for bank in banks:
        payload = {
            "name": bank['name'],
            "code": bank.get('code', ''),
            "account_number": bank.get('account_number', ''),
            "account_type": bank.get('account_type', 'current'),
            "iban": bank.get('iban', ''),
            "swift_code": bank.get('swift_code', ''),
            "is_active": bool(bank.get('is_active', 1)),
            "branch": bank.get('branch_id')
        }
        
        try:
            response = requests.post(f"{SERVER_URL}/banks/", json=payload)
            if response.status_code in [200, 201]:
                success += 1
            else:
                errors += 1
                if errors <= 3:
                    print(f"  خطأ في {bank['name']}: {response.text[:100]}")
        except Exception as e:
            errors += 1
            if errors <= 3:
                print(f"  استثناء: {e}")
    
    print(f"  ✓ نجح: {success} | ✗ فشل: {errors}")

def upload_suppliers(suppliers):
    """رفع الموردين"""
    print("\n📤 رفع الموردين...")
    success = 0
    errors = 0
    
    for i, supplier in enumerate(suppliers):
        payload = {
            "name": supplier['name'],
            "code": supplier['code'],
            "phone": supplier.get('phone', ''),
            "email": supplier.get('email', ''),
            "address": supplier.get('address', ''),
            "tax_number": supplier.get('tax_number', ''),
            "commercial_register": supplier.get('commercial_register', ''),
            "bank_name": supplier.get('bank_name', ''),
            "bank_account": supplier.get('bank_account', ''),
            "iban": supplier.get('iban', ''),
            "notes": supplier.get('notes', ''),
            "is_active": bool(supplier.get('is_active', 1))
        }
        
        try:
            response = requests.post(f"{SERVER_URL}/suppliers/", json=payload)
            if response.status_code in [200, 201]:
                success += 1
            else:
                errors += 1
                if errors <= 3:
                    print(f"  خطأ في {supplier['name']}: {response.text[:100]}")
        except Exception as e:
            errors += 1
            if errors <= 3:
                print(f"  استثناء: {e}")
        
        # طباعة التقدم كل 100 سجل
        if (i + 1) % 100 == 0:
            print(f"  ... تم معالجة {i + 1} من {len(suppliers)}")
    
    print(f"  ✓ نجح: {success} | ✗ فشل: {errors}")

def main():
    print("=" * 50)
    print("🔄 نقل البيانات من المحلي إلى الخادم")
    print("=" * 50)
    
    # استخراج البيانات المحلية
    print("\n📥 استخراج البيانات المحلية...")
    data = get_local_data()
    
    # رفع البيانات بالترتيب الصحيح (مراكز التكلفة أولاً لأن الفروع تعتمد عليها)
    upload_cost_centers(data['cost_centers'])
    upload_branches(data['branches'])
    upload_banks(data['banks'])
    upload_suppliers(data['suppliers'])
    
    print("\n" + "=" * 50)
    print("✅ اكتمل نقل البيانات!")
    print("=" * 50)

if __name__ == "__main__":
    main()
