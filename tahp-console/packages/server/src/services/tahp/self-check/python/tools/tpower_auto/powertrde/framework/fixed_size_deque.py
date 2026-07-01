class FixedSizeDeque:
    """
    极简的固定大小的环状双端队列，容量满了自动挤出最前端的数据，不用移动内存，效率很高
    """

    # 添加一个内部迭代器类，方便遍历
    class Iterator:
        def __init__(self, deque: 'FixedSizeDeque'):
            self.deque = deque
            self.index = 0

        def __iter__(self):
            return self

        def __next__(self):
            if self.index >= self.deque.size():
                raise StopIteration
            result = self.deque.get(self.index)
            self.index += 1
            return result

    def __init__(self, capacity):
        if capacity <= 0:
            raise ValueError("capacity can not be zero")
        self.capacity = capacity
        self.deque = []
        self.head_index = 0

    def add(self, element):
        if len(self.deque) == self.capacity:
            self.deque[self.head_index] = element
            self.head_index = (self.head_index + 1) % self.capacity
        else:
            self.deque.append(element)

    def get(self, index):
        if index >= min(self.capacity, len(self.deque)):
            raise IndexError("list index out of range")

        # 由于是环形缓冲区，需要重新计算实际索引
        return self.deque[(self.head_index + index) % self.capacity]

    def clear(self):
        self.deque.clear()
        self.head_index = 0

    def __getitem__(self, index):
        return self.get(index)

    def size(self):
        return len(self.deque)

    def __iter__(self):
        return FixedSizeDeque.Iterator(self)

    def __str__(self):
        return str([self.get(i) for i in range(self.size())])

