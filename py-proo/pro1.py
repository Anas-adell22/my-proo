def sum(x,y):
    return x+y

def sub(x,y):
    return x-y

def mul(x,y):
    return x*y

def mod(x,y):
    return x/y

print('whhat is the operation')
z=input()
print('enter the numbers')
x=int(input())
y=int(input())
if z== 'sum' :
    print(sum(x,y))
elif z== 'sub':
    print(sub(x,y))
elif z=='mul':
    print(mul(x,y))
else :
    print(mod(x,y))
