# https://gist.github.com/rouseguy/1122811f2375064d009dac797d59bae9
import numpy as np
import math
import time
import mxnet as mx
import mxnet.ndarray as nd
import logging
import sys
import os

logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)  # Config the logging
np.random.seed(777)
mx.random.seed(777)

digit = "0123456789"
alpha = "abcdefghij"

char_set = list(set(digit + alpha))  # id -> char
char_dic = {w: i for i, w in enumerate(char_set)}

data_dim = len(char_set)  # one hot encoding size
seq_length = time_steps = 7
num_classes = len(char_set)
batch_size = 32
seq_num = 1000

# Build training date set
dataX = np.empty(shape=(seq_num, seq_length), dtype=np.int)
dataY = np.empty(shape=(seq_num, seq_length), dtype=np.int)

for i in range(1000):
    rand_pick = np.random.choice(10, seq_length)
    dataX[i, :] = [char_dic[digit[c]] for c in rand_pick]
    dataY[i, :] = [char_dic[alpha[c]] for c in rand_pick]

# Build the symbol
data = mx.sym.var('data')  # Shape: (N, T)
target = mx.sym.var('target')  # Shape: (N, T)
lstm1 = mx.rnn.LSTMCell(num_hidden=32, prefix="lstm1_")
lstm2 = mx.rnn.LSTMCell(num_hidden=32, prefix="lstm2_")
data_one_hot = mx.sym.one_hot(data, depth=data_dim)  # Shape: (N, T, C)
data_one_hot = mx.sym.transpose(data_one_hot, axes=(1, 0, 2))  # Shape: (T, N, C)
_, encode_state = lstm1.unroll(length=seq_length, inputs=data_one_hot, layout="TNC")
encode_state_h = encode_state[0]  # Shape: (N, C)
encode_state_h = mx.sym.expand_dims(encode_state_h, axis=0)
encode_state_h = mx.sym.broadcast_to(encode_state_h, shape=(seq_length, 0, 0))  # Shape: (T, N, C)
decode_out, _ = lstm2.unroll(length=seq_length, inputs=encode_state_h, layout="TNC",
                             merge_outputs=True)
decode_out = mx.sym.reshape(decode_out, shape=(-1, 32))
logits = mx.sym.FullyConnected(decode_out, num_hidden=data_dim, name="logits")
logits = mx.sym.reshape(logits, shape=(seq_length, -1, data_dim))
logits = mx.sym.transpose(logits, axes=(1, 0, 2))
loss = mx.sym.mean(-mx.sym.pick(mx.sym.log_softmax(logits), target, axis=-1))
loss = mx.sym.make_loss(loss)

# Construct the training and testing modules
data_desc = mx.io.DataDesc(name='data', shape=(batch_size, seq_length), layout='NT')
label_desc = mx.io.DataDesc(name='target', shape=(batch_size, seq_length), layout='NT')
net = mx.mod.Module(symbol=loss,
                    data_names=['data'],
                    label_names=['target'],
                    context=mx.gpu())
net.bind(data_shapes=[data_desc], label_shapes=[label_desc])
net.init_params(initializer=mx.init.Xavier())
net.init_optimizer(optimizer="adam",
                   optimizer_params={'learning_rate': 1E-3,
                                     'rescale_grad': 1.0},
                   kvstore=None)

# We build another testing network that outputs the logits.
test_net = mx.mod.Module(symbol=logits,
                         data_names=[data_desc.name],
                         label_names=None,
                         context=mx.gpu())
# Setting the `shared_module` to ensure that the test network shares the same parameters and
#  allocated memory of the training network
test_net.bind(data_shapes=[data_desc],
              label_shapes=None,
              for_training=False,
              grad_req='null',
              shared_module=net)

begin = time.time()
for epoch in range(100):
    avg_cost = 0
    total_batch = int(math.ceil(dataX.shape[0] / batch_size))
    shuffle_ind = np.random.permutation(np.arange(dataX.shape[0]))
    dataX = dataX[shuffle_ind, :]
    dataY = dataY[shuffle_ind]
    for i in range(total_batch):
        # Slice the data batch and target batch.
        # Note that we use np.take to ensure that the batch will be padded correctly.
        data_npy = np.take(dataX,
                           indices=np.arange(i * batch_size, (i+1) * batch_size),
                           axis=0,
                           mode="clip")
        target_npy = np.take(dataY,
                             indices=np.arange(i * batch_size, (i + 1) * batch_size),
                             axis=0,
                             mode="clip")
        net.forward_backward(data_batch=mx.io.DataBatch(data=[nd.array(data_npy)],
                                                        label=[nd.array(target_npy)]))
        loss = net.get_outputs()[0].asscalar()
        avg_cost += loss / total_batch
        net.update()
    print('Epoch:', '%04d' % (epoch + 1), 'cost =', '{:.9f}'.format(avg_cost))
print('Learning Finished!')
end = time.time()
print("Total Time Spent: %gs" %(end - begin))
