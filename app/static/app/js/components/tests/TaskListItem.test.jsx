import React from 'react';
import { shallow } from 'enzyme';
import TaskListItem from '../TaskListItem';
import { createBrowserHistory } from 'history';

const taskMock = {
  id: 'task-1',
  project: 1,
  name: 'Mock task',
  status: 10,
  processing_time: 120000,
  estimated_time_remaining: 300000,
  import_url: '',
  last_error: '',
  processing_node: 1,
  pending_action: 3,
  partial: false,
  resize_progress: 0.35,
  upload_progress: 0,
  running_progress: 0.55,
  images_count: 50,
  tags: '',
  available_assets: [],
  compacted: false,
  uuid: 'uuid-1'
};

describe('<TaskListItem />', () => {
  it('renders without exploding', () => {
  	const wrapper = shallow(<TaskListItem history={createBrowserHistory()} data={taskMock} hasPermission={() => true} />);
    expect(wrapper.exists()).toBe(true);
  });

  it('renders the status label inside a dedicated status slot', () => {
    const wrapper = shallow(<TaskListItem history={createBrowserHistory()} data={taskMock} hasPermission={() => true} />);
    expect(wrapper.find('.status-slot').exists()).toBe(true);
    expect(wrapper.find('.status-slot .status-label').exists()).toBe(true);
  });
});
